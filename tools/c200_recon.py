#!/usr/bin/env python3
"""
Offline reconnaissance of a Samsung Gear 360 (SM-C200) over its own Wi-Fi AP.

WHY THIS IS A SCRIPT AND NOT A SESSION OF INTERACTIVE COMMANDS:
joining the camera's access point takes the computer off the internet, so
nothing interactive can run while it is connected. Run this while offline; it
writes everything to a timestamped directory, then reconnect and read it.

WHAT IT DOES: read-only observation. It sends GETs, one standard OSC state
query, and TCP connects. It does NOT take pictures, change any setting, write
anything to the camera, or modify the SD card. Safe on a bone-stock unit.

USAGE
    1. Put the camera into a mode that raises its AP (e.g. Google Street View).
    2. Join that AP from this computer.
    3. python3 c200_recon.py
    4. Rejoin your normal network. The output directory holds the results.

The single most important line in the output is whether TCP 7679 is OPEN --
that is the live-stream (remote viewfinder) port. Whether it binds without an
Android phone in the loop is, as of this writing, an open question.
"""
import json
import os
import socket
import ssl  # noqa: F401  (imported so a stdlib-less environment fails loudly here)
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# The camera's own documented HTTP surface, plus the usual suspects.
PRIORITY_PORTS = [
    (21, "FTP (only on modded units)"),
    (23, "telnet (only on modded units)"),
    (53, "DNS - seen open on C200"),
    (80, "HTTP / OSC API"),
    (443, "HTTPS"),
    (554, "RTSP"),
    (2869, "UPnP event"),
    (5555, "adb"),
    (7676, "Samsung AllShare httpd - seen open on C200"),
    (7677, "(adjacent to AllShare)"),
    (7678, "(adjacent to AllShare)"),
    (7679, "*** LIVE STREAM / RVF - THE ONE THAT MATTERS ***"),
    (7680, "(adjacent to stream port)"),
    (8080, "HTTP alt"),
    (8888, "HTTP control (R210 mod uses this)"),
    (9001, "HTTP file server (DCIM) - seen open on C200"),
]
SWEEP_RANGE = range(1, 10001)
CONNECT_TIMEOUT = 1.0
HTTP_TIMEOUT = 8
# Concurrency is deliberately modest. At 200 workers a validation run against a
# known-good host reported ports 80/443/8080 as CLOSED seconds after a serial
# probe found them OPEN -- the connections were being starved into timeout. A
# false "7679 closed" is the single most damaging wrong answer this script could
# produce, so the sweep trades speed for not lying.
SWEEP_WORKERS = 48

# The User-Agent the camera's own app uses. The device has been observed
# answering 503 to generic clients on its DLNA surface.
UA_APP = "Android Linux"
UA_RVF = "SEC_RVF_ML_02:00:00:00:00:00"


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=15).stdout.strip()
    except Exception as e:
        return "ERROR: %s" % e


def default_gateway():
    out = sh("netstat -rn | awk '$1==\"default\" && $2 ~ /[0-9]/ {print $2; exit}'")
    return out or None


def probe_port(ip, port, timeout=CONNECT_TIMEOUT):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return port
    except Exception:
        return None
    finally:
        s.close()


def probe_port_stubborn(ip, port, attempts=3, timeout=2.5):
    """For ports where a false negative would be expensive. Any hit wins."""
    for _ in range(attempts):
        if probe_port(ip, port, timeout=timeout) is not None:
            return True
        time.sleep(0.2)
    return False


def scan(ip, ports, workers=SWEEP_WORKERS):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return sorted(p for p in ex.map(lambda p: probe_port(ip, p), ports) if p)


def http(url, ua=UA_APP, method="GET", body=None, limit=200000):
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("User-Agent", ua)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return {"url": url, "ua": ua, "status": r.status,
                    "headers": dict(r.headers),
                    "body": r.read(limit).decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return {"url": url, "ua": ua, "status": e.code,
                "headers": dict(e.headers or {}),
                "body": (e.read(limit) or b"").decode("utf-8", "replace")}
    except Exception as e:
        return {"url": url, "ua": ua, "error": "%s: %s" % (type(e).__name__, e)}


def peek_stream(ip, port, path, ua, outpath, seconds=6):
    """Open the stream port and record whatever bytes arrive. Read-only."""
    result = {"target": "http://%s:%d%s" % (ip, port, path), "ua": ua}
    try:
        s = socket.create_connection((ip, port), timeout=5)
        s.settimeout(seconds)
        req = ("GET %s HTTP/1.1\r\nUser-Agent: %s\r\nHost: %s:%d\r\n"
               "Connection: Keep-Alive\r\n\r\n" % (path, ua, ip, port))
        s.sendall(req.encode())
        buf, start = b"", time.time()
        while time.time() - start < seconds:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            if len(buf) > 4 * 1024 * 1024:
                break
        s.close()
        head, _, tail = buf.partition(b"\r\n\r\n")
        result["response_head"] = head.decode("latin-1", "replace")[:2000]
        result["payload_bytes"] = len(tail)
        result["payload_first_64_hex"] = tail[:64].hex()
        result["payload_first_64_ascii"] = "".join(
            chr(b) if 32 <= b < 127 else "." for b in tail[:64])
        result["looks_like_TTTS"] = tail[:4] == b"TTTS"
        if tail:
            with open(outpath, "wb") as f:
                f.write(tail)
            result["saved_to"] = outpath
    except Exception as e:
        result["error"] = "%s: %s" % (type(e).__name__, e)
    return result


def main():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.abspath("c200-recon-%s" % stamp)
    os.makedirs(outdir, exist_ok=True)
    report = {"timestamp": stamp}

    def say(m):
        print(m, flush=True)

    say("=" * 68)
    say("Gear 360 SM-C200 recon  ->  %s" % outdir)
    say("=" * 68)

    report["ifconfig_en0"] = sh("ipconfig getifaddr en0")
    report["routing_table"] = sh("netstat -rn -f inet | head -20")
    report["wifi"] = sh("networksetup -getairportnetwork en0")
    gw = default_gateway()
    report["default_gateway"] = gw
    say("\n[1] This machine: %s   via %s" % (report["ifconfig_en0"] or "?", report["wifi"] or "?"))
    say("    Default gateway (expected to BE the camera): %s" % gw)

    if not gw:
        say("\n!! No default gateway. Are you actually joined to the camera's AP?")
        say("   Continuing anyway with 192.168.107.1 as a fallback guess.")
        gw = "192.168.107.1"

    cam = gw
    report["camera_ip"] = cam

    say("\n[2] Reachability")
    report["ping"] = sh("ping -c 3 -W 2000 %s" % cam)
    reachable = "0.0% packet loss" in report["ping"] or "bytes from" in report["ping"]
    say("    ping %s -> %s" % (cam, "OK" if reachable else "NO REPLY"))

    say("\n[3] Priority port probe")
    open_priority = []
    for port, note in PRIORITY_PORTS:
        is_open = probe_port(cam, port) is not None
        if is_open:
            open_priority.append(port)
        say("    %-6d %-8s %s" % (port, "OPEN" if is_open else "closed", note))
    report["priority_ports_open"] = open_priority

    say("\n[4] Full sweep 1-10000 (a few minutes; deliberately not aggressive)")
    swept = scan(cam, SWEEP_RANGE)
    # Union with the serial probe. The sweep can produce false negatives under
    # load; it must never be allowed to retract a port the serial probe saw.
    all_open = sorted(set(swept) | set(open_priority))
    missed = sorted(set(open_priority) - set(swept))
    report["sweep_raw"] = swept
    report["all_open_ports"] = all_open
    report["sweep_false_negatives"] = missed
    say("    open: %s" % (all_open or "(none)"))
    if missed:
        say("    (sweep missed %s under load; serial probe wins)" % missed)

    say("\n[5] HTTP surfaces")
    probes = {
        "osc_info": ("http://%s/osc/info" % cam, UA_APP, "GET", None),
        "osc_info_8080": ("http://%s:8080/osc/info" % cam, UA_APP, "GET", None),
        "osc_state": ("http://%s/osc/state" % cam, UA_APP, "POST", b""),
        "root_80": ("http://%s/" % cam, UA_APP, "GET", None),
        "allshare_7676_smp2": ("http://%s:7676/smp_2_" % cam, UA_RVF, "GET", None),
        "allshare_7676_root": ("http://%s:7676/" % cam, UA_RVF, "GET", None),
        "files_9001": ("http://%s:9001/" % cam, UA_APP, "GET", None),
    }
    http_results = {}
    for name, (url, ua, method, body) in probes.items():
        r = http(url, ua=ua, method=method, body=body)
        http_results[name] = r
        tag = r.get("status", r.get("error", "?"))
        say("    %-22s %s" % (name, tag))
        if name == "osc_info" and r.get("body"):
            try:
                info = json.loads(r["body"])
                report["osc_info_parsed"] = info
                say("        model=%s  firmware=%s  apiLevel=%s"
                    % (info.get("model"), info.get("firmwareVersion"), info.get("apiLevel")))
                api = info.get("api") or []
                say("        api endpoints: %d -> %s" % (len(api), ", ".join(api)))
                # NOTE: do NOT look for camera.getLivePreview in this array.
                # `api` lists protocol ENDPOINTS, not command names; on a
                # level-1 camera it is always the same five. getLivePreview is
                # a command posted to /osc/commands/execute, so its absence
                # here proves nothing. An earlier version of this script
                # reported "getLivePreview present: NO" from this array and
                # would have falsely closed the OSC path. Use osc_probe.py --
                # it sends the commands and reads the errors.
                say("        (command support is NOT visible here -- run osc_probe.py)")
            except Exception:
                pass
    report["http"] = http_results

    say("\n[6] Live-stream port 7679 -- the decisive test")
    # Re-checked on its own terms: 3 attempts, generous timeout. A false
    # negative here would wrongly close off the phone-free path.
    stream_open = probe_port_stubborn(cam, 7679)
    report["port_7679_open"] = stream_open
    say("    stubborn re-check of 7679 (3 attempts, 2.5s each): %s"
        % ("OPEN" if stream_open else "closed"))
    if stream_open:
        say("    7679 is OPEN with no phone in the loop. Attempting to read bytes.")
        report["stream_app_ua"] = peek_stream(
            cam, 7679, "/livestream_high.avi", UA_APP,
            os.path.join(outdir, "stream_app_ua.bin"))
        report["stream_rvf_ua"] = peek_stream(
            cam, 7679, "/livestream_high.avi", UA_RVF,
            os.path.join(outdir, "stream_rvf_ua.bin"))
        for k in ("stream_app_ua", "stream_rvf_ua"):
            r = report[k]
            say("    %-16s %s  bytes=%s  TTTS=%s" % (
                k, (r.get("response_head", "").splitlines() or [r.get("error", "?")])[0],
                r.get("payload_bytes"), r.get("looks_like_TTTS")))
    else:
        say("    7679 CLOSED in this mode. That is an informative result, not a failure:")
        say("    it means the port binds only once remote-viewfinder mode is triggered.")
        report["stream_note"] = "7679 closed in this camera mode"

    with open(os.path.join(outdir, "report.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    for name, r in http_results.items():
        if r.get("body"):
            with open(os.path.join(outdir, "http_%s.txt" % name), "w") as f:
                f.write("%s\nUA: %s\nstatus: %s\n\n%s\n\n%s" % (
                    r["url"], r["ua"], r.get("status"),
                    json.dumps(r.get("headers", {}), indent=2), r["body"]))

    say("\n" + "=" * 68)
    say("DONE. Results in: %s" % outdir)
    say("Rejoin your normal Wi-Fi. Nothing was written to the camera.")
    say("=" * 68)


if __name__ == "__main__":
    sys.exit(main())
