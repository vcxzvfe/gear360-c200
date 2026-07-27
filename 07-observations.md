# Hardware observations

Measurements from real SM-C200 units. Everything here is `[VERIFIED]` unless
marked otherwise, and every entry names the unit's firmware build — on this
camera the build matters more than anything else.

Units in this log:

| Label | Firmware | Notes |
|---|---|---|
| Unit A | `C200GLU0AQK1` | final build, 2017-11-21 |
| Unit B | `C200GLU0APC9` | oldest documented build |

---

## 2026-07-27 — `Google Street View` menu entry is firmware-dependent

`[VERIFIED]` **Unit A (`AQK1`): absent. Unit B (`APC9`): present.** Both with a
memory card inserted, both press-and-hold Menu.

The English launch manual (05/2016, Rev. 1.0) documents three press-and-hold
entries: `Gear 360 Manager`, `Remote control`, `Google Street View`. On `AQK1`
only the first two appear.

Two hypotheses were tested and **both refuted**:

- *"It is a China-region firmware with Google features stripped."* Refuted: the
  unit that lacks the entry reports `Software = C200GLU0AQK1` in photo EXIF —
  the **global** build.
- *"No memory card is inserted."* Refuted: the entry stayed absent on `AQK1`
  with a card in. (The card does matter for other menu items — the C200 has no
  internal storage — but it is not the cause here.)

`[INFERRED]` Remaining explanation: the entry was removed somewhere between
`APC9` and `AQK1`. The intermediate builds (`APE4`, `API1`, `AQC1`, `AQF1`) are
untested. **If you own a C200 on one of those, reporting present/absent would
close this.**

**Consequence:** on `AQK1` the whole OSC surface below is unreachable from the
camera body. Do not update a working `APC9` unit.

## 2026-07-27 — Firmware version is readable two ways, no phone needed

`[VERIFIED]` Photo EXIF `Software` field and OSC `/osc/info` `firmwareVersion`
**agree independently** on Unit B: both `C200GLU0APC9`.

This matters because prior write-ups (and earlier drafts of this repository)
said the firmware version was only visible through the Samsung phone app. It is
not. Either channel works with no phone, no app, and no modification:

```bash
exiftool -Software /Volumes/*/DCIM/*/*.JPG          # any unit that can shoot
curl -s http://192.168.107.1/osc/info               # units with Street View mode
```

---

## 2026-07-27 — First published `/osc/info` from an SM-C200

Unit B, `C200GLU0APC9`, in Google Street View mode, camera at `192.168.107.1`,
client assigned `192.168.107.103`. Serial redacted.

```json
{
  "manufacturer": "Samsung Electronics",
  "model": "GEAR 360",
  "serialNumber": "R3AH2xxxxxx",
  "firmwareVersion": "C200GLU0APC9",
  "supportUrl": "www.samsung.com",
  "endpoints": { "httpPort": 80, "httpUpdatePort": 80 },
  "gps": false,
  "gyro": false,
  "uptime": 50,
  "api": [
    "/osc/info", "/osc/state", "/osc/checkForUpdates",
    "/osc/commands/execute", "/osc/commands/status"
  ]
}
```

`/osc/state` returns:

```json
{ "fingerprint": "ABCD1234",
  "state": { "sessionId": "SID_0000", "batteryLevel": 1.000000 } }
```

Notes on this dump:

- **`apiLevel` is absent.** Per the OSC specification an absent `apiLevel`
  means **level 1**. Consistent with baardove's description of this camera.
- **The `api` array lists ENDPOINTS, not commands.** These five are the fixed
  level-1 endpoint set. `camera.getLivePreview` is a command name posted to
  `/osc/commands/execute` and would never appear here. **An earlier version of
  `tools/c200_recon.py` searched this array for it and reported
  "getLivePreview present: NO", which proved nothing and would have falsely
  closed the OSC path.** Fixed; use `tools/osc_probe.py`, which sends commands
  and reads the errors. `[UNKNOWN]` — still unanswered as of this writing.
- **`gyro: false`** — yet the RVF stream's TTTS container carries a `VRO0` /
  `00VR` orientation track. The two claims are in tension and neither has been
  checked against a decoded frame.
- **`fingerprint: "ABCD1234"`** is a placeholder value, and the HTTP `Date`
  header read `Thu, 31 Dec 2015` — the clock is unset without a phone. Both
  support Mapillary's characterisation of this camera as *"semi OSC
  compliant"*.

---

## 2026-07-27 — The open-port set depends on the camera's mode

`[VERIFIED]` Unit B in **Street View / OSC mode** (camera's own SoftAP), full
TCP sweep 1–10000:

```
open: 53, 80
```

`[COMMUNITY]` The port set previously recorded for this camera — `53, 7676,
9001` — was measured over **Wi-Fi Direct**, a different mode.

**These are different service sets, and this repository previously conflated
them.** The camera is not one network target with one port list; it presents
different services per mode.

| Mode | Camera address | Observed open |
|---|---|---|
| Street View / OSC (SoftAP) | `192.168.107.1` `[VERIFIED]` | `53, 80` `[VERIFIED]` |
| Wi-Fi Direct | `192.168.49.10` `[COMMUNITY]` | `53, 7676, 9001` `[COMMUNITY]` |

### Consequences

1. **7679 is closed in Street View mode**, re-checked three times at a 2.5 s
   timeout. Triggering the live stream by entering Street View mode **does not
   work.** That shortcut is closed.
2. **7676 is also closed in Street View mode.** So the SOAP `changeToRVF`
   trigger (Experiment 8) **cannot even be attempted from this mode** — the
   UPnP/AllShare surface it targets is not listening. Experiment 8 needs a mode
   that raises 7676, and which mode that is on a SoftAP the Mac can join is
   `[UNKNOWN]`.
3. `192.168.107.1` is confirmed on `APC9`, matching baardove's observation from
   a 2016 unit. Do not treat it as universal — read your own gateway.

---

## Open, and cheap to answer next

1. **What does `Remote control` mode do?** It is the third press-and-hold entry,
   the manual never explains it, and nobody has documented it. Does it raise an
   AP? Does it bind 7676 or 7679? Running `tools/c200_recon.py` in that mode is
   zero-risk and could reopen the phone-free path that Street View mode closed.
2. **Does the OSC endpoint accept any live-preview command?** Genuinely open —
   see the correction above. `tools/osc_probe.py` answers it.
3. **Which build removed the Street View entry?** Needs a unit on `APE4`,
   `API1`, `AQC1` or `AQF1`.

---

## 2026-07-27 — OSC is definitively closed for live video

Unit B, `C200GLU0APC9`, Street View mode. Every live-preview command spelling
returns `unknownCommand`:

```
camera.getLivePreview            -> 400 {"code":"unknownCommand"}
camera._getLivePreview           -> 400 {"code":"unknownCommand"}
camera.getLivePreview {_mode}    -> 400 {"code":"unknownCommand"}
camera._getPreview               -> 400 {"code":"unknownCommand"}
camera.getPreview                -> 400 {"code":"unknownCommand"}
```

By the criterion this repository set in advance — `unknownCommand` closes the
question, any other error would mean the command exists — **Path 2 (OSC) is
closed for live video.** `[VERIFIED]` This supersedes the earlier non-result
that came from misreading the `api` array.

What does work: `camera.startSession` (returns e.g. `SID_0216`, timeout 300),
`camera.closeSession`, `camera.listImages`.

**The most informative result is `camera.getOptions`.** Asked for ten option
names, the camera returned exactly one:

```json
{"name":"camera.getOptions","state":"done","results":{"options":{"captureMode":"image"}}}
```

`previewFormat`, `previewFormatSupported`, `captureModeSupported`,
`fileFormat`, `exposureProgram`, `remainingPictures`, `totalSpace`,
`remainingSpace` and `_liveStream` were **silently dropped** rather than
producing the error the specification requires. This is a minimum-viable OSC
implementation built to hand stills to the Street View app, with no video
surface at all. Do not spend further effort here.

## 2026-07-27 — `Remote control` mode raises no Wi-Fi

`[COMMUNITY — operator report]` On `APC9`, entering `Remote control` shows a
pairing indication and **no joinable Wi-Fi network appears**; a Mac cannot
connect to it.

`[INFERRED]` It is a **Bluetooth** mode. The manual's LED table lists
`Red → Green → Blue = Bluetooth pairing mode`, and of the three press-and-hold
entries `Gear 360 Manager` is explicitly "Enter Bluetooth pairing mode". So
`Remote control` is most likely a Bluetooth shutter/remote pairing mode, not a
network mode.

**Consequence:** it does not reopen the 7676 (SOAP) or 7679 (stream) surfaces,
and the hope that it might be a phone-free route to RVF is not supported.
`[UNKNOWN]` whether macOS can pair with it at all, or what profile it exposes.

---

## 2026-07-27 — TTTS demuxer built and validated (no camera required)

`[VERIFIED-EXTRACTED]` The container specification came out of the camera's own
muxer, `cTTTWriter` in `/usr/lib/libmmfcore.so`, so the desktop side could be
built before the trigger problem is solved. See `08-firmware-teardown.md` §1.4(c).

**A prior implementation in this repository was wrong and has been removed.**
`tools/ttt_demux.py` was reconstructed from the Android app and parsed a
structured header containing a `VRO0` / `00VR` orientation track. The firmware
writes `ACC0` / `AC00`, and a byte scan of all 11,567 files in the extracted
root filesystem finds **zero** occurrences of `VRO0` or `00VR`. Its header
parser would also have desynced: the header frame is a fixed 224 bytes, which
is the firmware's own log text, not a set of walkable sub-records. Keeping two
demuxers that disagree is worse than keeping one; it is in git history.

`tools/ttts.py` replaces it. `tests/test_ttts.py` has 17 unit tests over
synthetic containers — including byte-granularity independence, since a socket
returns short reads and that is the classic way this kind of parser silently
corrupts a stream — and one test that asserts `00VR` is **rejected**, so that if
a real capture ever does contain it, the failure is loud rather than silent.

`tests/test_ttts_e2e.py` closes the gap the unit tests cannot: ffmpeg encodes
real HEVC at the camera's own 2560×1280, it is split at access-unit boundaries
with parameter sets leading their keyframe (as the muxer does), wrapped in TTTS,
demuxed, and then **decoded back to pixels**. Byte-identity is asserted against
the original elementary stream. Both integration tests pass on this machine
with libx265 present.

**What this does and does not establish.** It establishes that *if* the
specification is right, this code produces playable video. It does **not**
establish that the specification matches what the camera emits — nothing but a
capture from real hardware can do that, and none exists yet, by anyone. The
first person to capture one should keep the raw container bytes
(`ttts_capture.py --raw`), because that artifact has never been published.
