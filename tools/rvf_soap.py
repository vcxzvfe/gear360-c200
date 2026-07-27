#!/usr/bin/env python3
"""Try to drive an SM-C200 into remote-view-finder mode over the network, then stream.

This fires the SetOperationState(changeToRVF) SOAP request that was recovered
verbatim from the camera's own libdi-network-dlna-rvf.so during the firmware
teardown (08-firmware-teardown.md section 1.4). That request had never been
captured on the wire by anyone; this is the first tool that sends it.

WHAT IT IS FOR RIGHT NOW: a zero-risk probe. Bench measurement shows that in
Street View / OSC mode the camera opens only TCP 53 and 80 -- 7676 is closed,
so the SOAP has nowhere to land and this is EXPECTED to report a refused
connection. Running it anyway definitively closes the question of whether the
UPnP control surface is reachable without a Bluetooth trigger. If 7676 is ever
found open (a different mode, or after a root-side trigger), this same tool
completes the sequence and hands off to the demuxer.

It sends only a documented UPnP control request and HTTP GETs. It writes
nothing to the camera.

USAGE
    python3 rvf_soap.py 192.168.107.1                 # probe + (if it works) stream
    python3 rvf_soap.py 192.168.107.1 --info-only     # only read what is reachable
    python3 rvf_soap.py 192.168.107.1 --out cam.hevc  # save demuxed HEVC
"""

from __future__ import annotations

import argparse
import socket
import sys
import urllib.error
import urllib.request

try:
    from ttts import (  # when run from the tools/ directory
        STREAM_PATHS,
        USER_AGENT_RVF_PREFIX,
        demux_video,
        open_stream,
    )
except ImportError:  # when imported as tools.rvf_soap
    from tools.ttts import (
        STREAM_PATHS,
        USER_AGENT_RVF_PREFIX,
        demux_video,
        open_stream,
    )

# The control surface lives on 7676.
#
# CORRECTION, from a real SD card that had been in a Gear 360: the device's own
# DeviceDescription.xml (written by the camera to
# /mnt/mmc/.config/RVF/xml/DeviceDescription.xml) maps the ContentDirectory
# service as:
#     controlURL  /smp_4_
#     eventSubURL /smp_5_
#     SCPDURL     /smp_3_
# The firmware teardown, reading a template out of libdi-network-dlna-rvf.so,
# reported controlURL=/smp_3_ and SCPDURL=/smp_5_ -- i.e. rotated. An earlier
# version of this file followed the teardown and would have POSTed the SOAP at
# the SCPD document instead of the control endpoint.
#
# The card is the authoritative artifact: it is what the camera actually
# serves. But since the card and the library template disagree, and a card may
# have come from a different firmware than the unit under test, the tool reads
# the device description at run time when it can, and falls back to trying both
# mappings rather than trusting either constant.
CONTROL_PORT = 7676
STREAM_PORT = 7679
CONTROL_URL = "/smp_4_"
SCPD_URL = "/smp_3_"
CONTROL_URL_FALLBACKS = ("/smp_4_", "/smp_3_")
#: Where the device description itself is served. Reading this settles the
#: mapping for whatever unit is actually in front of you.
DEVICE_DESC_PATHS = ("/smp_0_", "/smp_1_", "/smp_2_", "/dmr", "/")
SERVICE_TYPE = "urn:schemas-upnp-org:service:ContentDirectory:1"

# The device derives control-point identity from the User-Agent by SUBSTRING
# match against the pattern "SEC_RVF_ML_" (.rodata @0x153af0). Whether the ACL
# is armed is unknown; sending the prefix costs nothing and is the first thing
# to try on a 503/401.
USER_AGENT = USER_AGENT_RVF_PREFIX + "mac"

# SetOperationState takes StateEvent. The SCPD DECLARES it as dataType ui4, but
# the handler (UPnPCDSRVFSetOperationState::get_operation_state_index @0x5fce8)
# does a case-insensitive STRING compare against "changeToRVF"/"changeToML".
# The SCPD lies; send the string.
STATE_RVF = "changeToRVF"

SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"'
    ' xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
    '<u:{action} xmlns:u="{svc}">{args}</u:{action}>'
    "</s:Body></s:Envelope>"
)

EXIT_OK = 0
EXIT_STREAM_ERROR = 1
EXIT_NO_CONTROL = 2


def _port_open(host: str, port: int, timeout: float = 4.0) -> bool:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def _http(host: str, port: int, path: str, *, method: str = "GET",
          body: bytes | None = None, headers: dict[str, str] | None = None,
          timeout: float = 10.0) -> tuple[int, dict[str, str], bytes]:
    url = f"http://{host}:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", USER_AGENT)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read(65536)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), (exc.read(65536) or b"")


def discover_control_url(host: str) -> str | None:
    """Read the device description and return the ContentDirectory controlURL.

    Trusting a hardcoded constant here is what produced the /smp_3_ vs /smp_4_
    mistake, so ask the device when it will answer.
    """
    import re

    for path in DEVICE_DESC_PATHS:
        status, _, body = _http(host, CONTROL_PORT, path)
        if status != 200 or b"ContentDirectory" not in body:
            continue
        text = body.decode("utf-8", "replace")
        for service in re.findall(r"<service>.*?</service>", text, re.S):
            if "ContentDirectory" not in service:
                continue
            match = re.search(r"<controlURL>\s*([^<\s]+)\s*</controlURL>", service)
            if match:
                return match.group(1)
    return None


def soap_action(host: str, action: str, args: str, control_url: str,
                timeout: float = 10.0) -> tuple[int, bytes]:
    """Send one SOAP action to the given control URL."""
    body = SOAP_ENVELOPE.format(action=action, svc=SERVICE_TYPE,
                                args=args).encode("utf-8")
    headers = {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": f'"{SERVICE_TYPE}#{action}"',
        "Connection": "close",
    }
    status, _, resp = _http(host, CONTROL_PORT, control_url, method="POST",
                            body=body, headers=headers, timeout=timeout)
    return status, resp


def soap_set_operation_state(host: str, state: str = STATE_RVF,
                             control_url: str | None = None,
                             timeout: float = 10.0) -> tuple[int, bytes, str]:
    """Send SetOperationState. Returns (status, body, control_url_used).

    If no control URL is given, the device description is consulted; failing
    that, every known mapping is tried rather than guessing one.
    """
    args = f"<StateEvent>{state}</StateEvent>"
    candidates = ([control_url] if control_url
                  else [discover_control_url(host) or ""] + list(CONTROL_URL_FALLBACKS))
    last: tuple[int, bytes, str] = (0, b"", "")
    for url in [c for c in candidates if c]:
        status, resp = soap_action(host, "SetOperationState", args, url, timeout)
        last = (status, resp, url)
        if status < 400:
            return last
    return last


def soap_get_information(host: str, control_url: str,
                         timeout: float = 10.0) -> tuple[int, bytes]:
    """GetInfomation (Samsung's spelling) returns StreamUrl once RVF is up.

    Its SCPD declares in: GPSINFO, out: GETINFORMATIONRESULT, StreamUrl.
    """
    return soap_action(host, "GetInfomation", "<GPSINFO></GPSINFO>",
                       control_url, timeout)


def probe(host: str) -> dict[str, object]:
    """Read whatever is reachable without changing anything."""
    report: dict[str, object] = {}
    report["control_port_7676_open"] = _port_open(host, CONTROL_PORT)
    report["stream_port_7679_open"] = _port_open(host, STREAM_PORT)
    if report["control_port_7676_open"]:
        status, _, body = _http(host, CONTROL_PORT, SCPD_URL)
        report["scpd_status"] = status
        report["scpd_len"] = len(body)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drive an SM-C200 into RVF via the recovered SOAP, then stream.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("host", help="camera address, e.g. 192.168.107.1")
    parser.add_argument("--path", default="/livestream_high.avi", choices=STREAM_PATHS)
    parser.add_argument("--out", help="write demuxed HEVC here (default: discard)")
    parser.add_argument("--raw", help="also save the untouched container bytes")
    parser.add_argument("--info-only", action="store_true",
                        help="probe and report; do not send the SOAP or stream")
    args = parser.parse_args(argv)

    def say(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    say(f"probing {args.host} ...")
    state = probe(args.host)
    say(f"  7676 (control): {'OPEN' if state['control_port_7676_open'] else 'closed'}")
    say(f"  7679 (stream):  {'OPEN' if state['stream_port_7679_open'] else 'closed'}")

    if not state["control_port_7676_open"]:
        say(
            "\n7676 is closed, so the SOAP has nowhere to go. On current evidence "
            "this is the expected result in Street View / OSC mode -- the control "
            "surface belongs to a subsystem that is not started there. It confirms "
            "the SOAP is NOT reachable without a Bluetooth or root-side trigger."
        )
        return EXIT_NO_CONTROL

    if args.info_only:
        say(f"\n7676 is open. SCPD GET returned {state.get('scpd_status')}, "
            f"{state.get('scpd_len')} bytes. Stopping (--info-only).")
        return EXIT_OK

    discovered = discover_control_url(args.host)
    if discovered:
        say(f"\n  device description says controlURL = {discovered}")
    else:
        say(f"\n  could not read the device description; will try "
            f"{', '.join(CONTROL_URL_FALLBACKS)} in turn")

    say("7676 is OPEN -- sending SetOperationState(changeToRVF) ...")
    status, resp, used = soap_set_operation_state(args.host, control_url=discovered)
    say(f"  SOAP -> HTTP {status}  (control URL {used})")
    if status < 400:
        info_status, info_body = soap_get_information(args.host, used)
        say(f"  GetInfomation -> HTTP {info_status}")
        if info_status < 400:
            import re
            url_match = re.search(rb"<StreamUrl>(.*?)</StreamUrl>", info_body, re.S)
            if url_match:
                say(f"  StreamUrl = {url_match.group(1).decode('utf-8', 'replace')}")
    if status in (401, 503):
        say("  refused by the User-Agent ACL despite the SEC_RVF_ML_ prefix. "
            "This is new information: the ACL is armed. Body:")
        say("  " + resp.decode("utf-8", "replace")[:400])
        return EXIT_STREAM_ERROR
    if status >= 400:
        say("  " + resp.decode("utf-8", "replace")[:400])
        return EXIT_STREAM_ERROR

    say("  accepted. Opening the stream ...")
    try:
        sock, head = open_stream(args.host, port=STREAM_PORT, path=args.path,
                                 user_agent=USER_AGENT)
    except OSError as exc:
        say(f"  stream port did not open after the trigger: {exc}")
        return EXIT_STREAM_ERROR

    say("  < " + head.split(b"\r\n", 1)[0].decode("latin-1", "replace"))

    import contextlib
    with contextlib.ExitStack() as stack:
        stack.callback(sock.close)
        out = (stack.enter_context(open(args.out, "wb")) if args.out
               else open("/dev/null", "wb"))

        class _Sock:
            def read(self, n: int) -> bytes:
                return sock.recv(n)

        source: object = _Sock()
        if args.raw:
            raw = stack.enter_context(open(args.raw, "wb"))

            class _Tee:
                def read(self, n: int) -> bytes:
                    data = sock.recv(n)
                    if data:
                        raw.write(data)
                    return data

            source = _Tee()

        stats = demux_video(source, out)  # type: ignore[arg-type]
        say(f"  {stats.video_chunks} video chunks, {stats.video_bytes} bytes HEVC")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
