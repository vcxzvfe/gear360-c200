#!/usr/bin/env python3
"""
Probe what the Gear 360 SM-C200 actually accepts on its OSC command endpoint.

WHY THIS EXISTS: an earlier version of the recon script concluded
"getLivePreview present: NO" by looking for it in the `api` array of
/osc/info. That was a category error. The `api` array lists the protocol's
ENDPOINTS -- on a level-1 camera it is always exactly these five:

    /osc/info  /osc/state  /osc/checkForUpdates
    /osc/commands/execute  /osc/commands/status

`camera.getLivePreview` is a COMMAND NAME posted to /osc/commands/execute, so
it was never going to appear there and its absence proved nothing. The only
way to know what the camera supports is to send the commands and read the
errors. That is what this does.

WHAT IT SENDS: read-only and session commands only.
  camera.startSession / closeSession   (normal client lifecycle, reversible)
  camera.getOptions                    (read)
  camera.listImages                    (read)
  camera.getLivePreview  + vendor-prefixed variants   (the actual question)
It does NOT take pictures, delete anything, change settings, or reset.

USAGE
    1. Put the camera in Google Street View mode (press-and-hold Menu).
       NOTE: this needs firmware that still has that entry -- it is present on
       C200GLU0APC9 and absent on C200GLU0AQK1.
    2. Join the camera's .OSC access point.
    3. python3 osc_probe.py            (or: python3 osc_probe.py 192.168.107.1)
    4. Rejoin your normal network and read the printed report.
"""
import json
import socket
import sys
import urllib.error
import urllib.request

TIMEOUT = 10
UA = "Android Linux"

# Commands worth asking about. Nothing here mutates stored content.
# The vendor-prefixed spellings matter: several level-1 cameras of this era
# (e.g. Ricoh Theta S) shipped live preview as an underscore-prefixed vendor
# extension rather than the level-2 standard name.
PROBE_COMMANDS = [
    ("camera.getLivePreview",   {}),
    ("camera._getLivePreview",  {}),
    ("camera.getLivePreview",   {"_mode": "preview"}),
    ("camera._getPreview",      {}),
    ("camera.getPreview",       {}),
    ("camera.listImages",       {"entryCount": 1, "includeThumb": False}),
    ("camera.getOptions",       {"optionNames": [
        "captureMode", "exposureProgram", "fileFormat", "previewFormat",
        "previewFormatSupported", "captureModeSupported", "_liveStream",
        "remainingPictures", "totalSpace", "remainingSpace",
    ]}),
]


def post(url, payload, raw=False):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            head = dict(r.headers)
            data = r.read(262144)
            return r.status, head, data
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), (e.read(262144) or b"")
    except Exception as e:
        return None, {}, ("%s: %s" % (type(e).__name__, e)).encode()


def show(status, head, data):
    ctype = head.get("Content-Type", "")
    print("      status=%s  content-type=%s  bytes=%d" % (status, ctype or "?", len(data)))
    if "multipart" in ctype.lower() or data[:2] == b"\xff\xd8":
        print("      *** LOOKS LIKE AN IMAGE / MJPEG STREAM -- THIS IS THE RESULT WE WANT ***")
        print("      first 32 bytes: %s" % data[:32].hex())
        return
    try:
        parsed = json.loads(data.decode("utf-8"))
        print("      " + json.dumps(parsed, ensure_ascii=False)[:800])
    except Exception:
        txt = data.decode("utf-8", "replace")[:400]
        print("      " + txt.replace("\n", "\n      "))


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.107.1"
    base = "http://%s" % ip
    exe = base + "/osc/commands/execute"

    print("=" * 66)
    print("OSC command probe -> %s" % ip)
    print("=" * 66)

    try:
        socket.create_connection((ip, 80), timeout=5).close()
    except Exception as e:
        print("Cannot reach %s:80 (%s). Are you joined to the camera's AP?" % (ip, e))
        return 1

    print("\n[1] camera.startSession  (level-1 cameras require a session)")
    status, head, data = post(exe, {"name": "camera.startSession",
                                    "parameters": {"timeout": 180}})
    show(status, head, data)
    session = None
    try:
        session = json.loads(data.decode())["results"]["sessionId"]
        print("      sessionId = %s" % session)
    except Exception:
        print("      (no sessionId parsed -- continuing without one)")

    print("\n[2] Command probes")
    for name, params in PROBE_COMMANDS:
        payload = {"name": name}
        p = dict(params)
        if session:
            p["sessionId"] = session
        if p:
            payload["parameters"] = p
        print("\n  -> %s  %s" % (name, json.dumps(params, ensure_ascii=False) if params else ""))
        show(*post(exe, payload))

    if session:
        print("\n[3] camera.closeSession  (tidy up)")
        show(*post(exe, {"name": "camera.closeSession",
                         "parameters": {"sessionId": session}}))

    print("\n" + "=" * 66)
    print("Read the errors, not just the successes. On this protocol an")
    print("unsupported command returns a JSON error naming itself -- that is")
    print("the evidence. 'unknownCommand' closes the question; anything else")
    print("(invalidParameterName, disabledCommand) means the command EXISTS.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
