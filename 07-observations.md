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

---

## 2026-07-27 — The recovered SOAP was fired at the camera. 7676 is not there.

Unit B, `C200GLU0APC9`, Street View / OSC mode, camera at `192.168.107.1`,
client `192.168.107.103`. Using `tools/rvf_soap.py`, which carries the
`SetOperationState(changeToRVF)` request recovered verbatim from
`libdi-network-dlna-rvf.so`:

```
7676 (control): closed
7679 (stream):  closed
```

Priority port probe in the same session — `53` and `80` open; `21, 23, 443,
554, 2869, 5555, 7676, 7677, 7678, 7679, 7680, 8080, 8888, 9001` all closed.

**This converts the chicken-and-egg from inference to measurement.** `[VERIFIED]`
The teardown *predicted*, from the firmware, that 7676 belongs to a subsystem
that Street View mode never starts. That prediction has now been tested by
actually sending the request: there is nothing listening to receive it. The
control surface is **not reachable without a Bluetooth or root-side trigger**.

Note on `9001`: the firmware teardown listed it as a port "nobody has probed".
That is true of the published community record, but this project had already
probed it in its first recon run, and it is closed in this mode too. Recorded
here so the teardown's to-do list is not carried forward as still-open.

### Where that leaves the routes

Everything reachable from outside a stock camera has now been tried and is
exhausted:

| Attempt | Result |
|---|---|
| OSC live-preview commands, five spellings | `unknownCommand` — closed |
| Street View mode as an RVF trigger | 7679 never binds — closed |
| The recovered SOAP, sent for real | 7676 not listening — closed |
| `Remote control` mode | raises no joinable Wi-Fi — closed |

`[VERIFIED]` **No zero-touch path remains.** The next move has to be Stage A of
the SD-card procedure (`09-root-procedure.md`) — which is still zero block
writes, but does put a card in the camera.

---

## 2026-07-27 — A used SD card carried the camera's own service description

An SD card that had been in a Gear 360 was found to contain
`/.config/` written by the camera itself. `[VERIFIED]` This is the authoritative
artifact for the RVF surface — it is what the camera actually serves — and it
is readable with no rooting, no trigger, and no risk. Anyone with a used
Gear 360 card already has it.

### It corrects the control URL, which would have broken the SOAP silently

The firmware teardown, reading a template out of `libdi-network-dlna-rvf.so`,
reported `controlURL=/smp_3_`, `eventSubURL=/smp_4_`, `SCPDURL=/smp_5_`.

The camera's own `DeviceDescription.xml` says otherwise:

```xml
<controlURL>/smp_4_</controlURL>
<eventSubURL>/smp_5_</eventSubURL>
<SCPDURL>/smp_3_</SCPDURL>
```

`[VERIFIED]` The mapping is rotated. **`tools/rvf_soap.py` was POSTing the SOAP
at `/smp_3_`, which is the read-only SCPD document, not the control endpoint.**
Since 7676 has never been open in any mode reached so far, this had not yet
produced a visible failure — it would have surfaced later as an inexplicable
error at the one moment the camera was finally cooperating. Fixed: the tool now
reads the device description at run time and falls back to trying both mappings
rather than trusting any constant.

### Ports the scans never covered

`UPnPConfig.xml`, verbatim:

```
WebServerPort                 5215
UPnPServerPort                5216
HTTPTCPServerPort             7676
HTTPUDPServerPort            24234
HTTPMulticastServerPort       1900
HTTPMulticastEventServerPort  7900
HTTPStreamingPort             7679
AutoAuthenticate                 0
```

and `http_stream.ini` gives `HTTPPort=9001`, `CDSPort=5301`,
`StreamDir=DCIM/100PHOTO/`.

`[VERIFIED]` This confirms 7676/7679/9001 independently of the disassembly. It
also shows **`24234` sits above the 1–10000 sweep this project has been running,
so it has never been scanned**, and `1900` is SSDP — a **UDP** port, while every
scan so far has been TCP-only. Neither is likely to answer in Street View mode
(the whole UPnP subsystem is unstarted there) but neither has been tested.

`AutoAuthenticate=0` is relevant to the teardown's open question about whether
the `SEC_RVF_ML_` User-Agent ACL is armed. It is suggestive, not conclusive —
it is a different mechanism from the ACL filter — but it points the same way.

### The full remote-control surface, from the camera's own SCPD

`ContentDirectory_1.xml` on the card declares **50 actions**. This is far more
than a stream: it is the complete remote control API, and it has not been
published before.

Relevant to this project: `SetOperationState` (the RVF switch), `GetInfomation`
(in: `GPSINFO`; out: `GETINFORMATIONRESULT`, **`StreamUrl`**), `SetStreamQuality`,
`StopStreaming`, `X_PauseStreaming`.

Beyond streaming: `Shot`, `StartRecord`, `StopRecord`, `StartShot`, `StopShot`,
`SetResolution`, `X_SetDualResolution`, `SetMovieResolution`,
`X_SetDualMovieResolution`, `SetEV`, `SetISO`, `SetWB`, `SetDialMode`,
`X_SetHDR`, `X_SetSharpness`, `X_SetWindCut`, `X_SetTimeLapse`,
`X_SetLoopingVideo`, `X_SetSwitchLens`, `X_SetTimer`, `X_IntervalShot`,
`X_SetInitialView`, `X_SetViewType`, `X_GetStorage`, `X_SetFormat`,
`X_DeleteFile`, `X_SetLED`, `X_SetBeep`, `X_SetAutoPowerOff`, `GetIP`, and more.

**Consequence:** once RVF is reachable, the camera is fully controllable over
plain SOAP — not just watchable. The `SetOperationState` argument
`ChangeStateEvent` is confirmed on the card as `<dataType>ui4</dataType>`, which
is exactly the declaration the teardown found the handler contradicts by doing a
case-insensitive string compare. Send `changeToRVF` as a string.

### Note on the card itself

`[VERIFIED]` The card in use here is **ExFAT**, not FAT32, and the camera had
clearly written to it (`DCIM`, `SYSTEM`, `.config`), so the camera reads ExFAT.
Whether `dfmsd` script mode also reads it is `[UNKNOWN]`; if the recon chain
does not fire, filesystem type is the second thing to vary after byte-exactness
of `info.tg`.

---

## 2026-07-27 — Stage-A root reconnaissance SUCCEEDED (Unit A, AQK1)

The `dfmsd` script chain fired on the first attempt. The ExFAT card worked; the
byte-exact `info.tg`/`recon.adj` worked. All 18 read-only outputs plus the
`DONE` marker were written to the card. Full set archived under
`research/recon-out-AQK1-20260727/`. This is the first published inside-the-box
data from an SM-C200.

### The headline results

**`id` → `uid=0(root) gid=0(root)`.** `[VERIFIED-DEVICE]` Root, with zero block
writes and a fully reversible card change.

**`uname` → `Linux drime5 3.5.0 #5 PREEMPT ... armv7l`.** `[VERIFIED-DEVICE]`
DRIMe5 SoC, kernel 3.5.0, ARMv7 (32-bit, little-endian) — the ABI any
cross-compiled binary must target, now confirmed on hardware rather than
inferred.

**`version.info`** confirms `SMC200GLU0AQK1`, `DSP_SMC200GLU0AQK1_DV1`,
platform version `0.85` — matches the firmware image header exactly.

### The port model is confirmed on hardware

`[VERIFIED-DEVICE]` `netstat -lntp` while `di-camera-app` (PID 252) was running
listed **zero listening TCP sockets.** The teardown's central claim — that
80/7676/7679/9001 are not daemons but are bound on demand when the app enters a
mode — is now confirmed directly: the app is up, and nothing is listening until
a mode is entered. This is exactly why every external probe found closed ports.

### V4L2 capture path is closed

`[VERIFIED-DEVICE]` `/dev/video0..2` and `/dev/media0` do **not exist**. Capture
is entirely behind the proprietary DRIMe5 API; there is no standard V4L2 node to
read. The non-RVF capture fallback (teardown §4) is therefore not reachable from
userspace. RVF is the only video path.

### The RVF trigger surface, live and introspected

`[VERIFIED-DEVICE]` `org.bt.app` at `/org/bt/app_service` exposes exactly one
real method, with its full signature read off the running system:

```
app_service_request(
    i  svc_type,      i  svc_function,   i  req_type,
    ay input1, ay input2, ay input3, ay input4, ay input5,
) -> ( i output1, v output2 )
```

This is the D-Bus method that Bluetooth commands travel through into
`di-camera-app`. **A root shell can call it directly**, short-circuiting the
entire Bluetooth/SAP transport that was route A's hard part. `org.bt.app_event`
introspects to an empty node (it is signal-only), so the request path is
`app_service_request`, not an event emit.

`sdbd` also came up on request and bound **`127.0.0.1:26099`** (localhost only —
so not directly reachable from the Mac without a port forward, but present).

### What is now the single remaining unknown

The three integers `svc_type / svc_function / req_type` that mean "liveview".
The teardown located `EXE_LIVEVIEW = 20` in the BT command vocabulary and the
handler `CUINETFuncBluetooth::handle_bt_app_receive_command`; the mapping from
that to the `app_service_request` argument triple has to come from disassembly
of `di-camera-app` around @0x241b08. Once that triple is known, a one-line
`dbus-send` from a card script starts RVF with no phone and no SAP — and Stage A
proved a card script runs as root.

**Project status:** the phone-free path is no longer blocked on an unknown
mechanism. It is blocked on three integers, recoverable from a binary already on
disk, then executable through a mechanism already proven to work.

---

## 2026-07-27 — Two consequential details from the recon dump

### A serial getty is running on ttyAMA0

`[VERIFIED-DEVICE]` `systemctl` shows `serial-getty@ttyAMA0.service ... loaded active
running`. The teardown had marked "UART usable on retail silicon" as `[UNKNOWN]` because the
released bootloader console defines targeted a dev board. This is a partial answer at the OS
level: **a login getty is live on ttyAMA0.** If the UART pads can be found and wired
(115200 8N1), that is a persistent root login shell independent of the SD card — a better
working channel than re-inserting a card each time, and a genuine rescue path if a later step
ever stops the system booting to `di-camera-app`. It does not prove the bootloader prompt is
reachable (that is what would rescue a bad kernel), only that the running system offers a
console login. Worth locating the pads on the AQK1 unit.

### dfmsd runs as a child of di-camera-app

`[VERIFIED-DEVICE]` `ps -ef`: `di-camera-app` is PID 252 (root); `dfmsd` is PID 288 with
PPID 252. So the SD-card script does not run in isolation at boot — it runs **while
di-camera-app is already up and the D-Bus system bus is available** (`dbus.service` running).
This is exactly the environment a D-Bus trigger needs: the target app and bus are live when
our script executes. It also means the app's own state machine is running, which matters if
the trigger must be delivered as an event the app is waiting for rather than a cold call.

### Filesystem writability, for the record

`[VERIFIED-DEVICE]` `/` is `ext4 ro`; `/opt` (`mmcblk0p10`) and `/opt/usr` (`mmcblk0p13`) are
`ext4 rw`; the SD card (`mmcblk1p1`) is `exfat rw`. So the root filesystem is read-only as
mounted — consistent with the teardown's warning that persistent rootfs edits require a
remount and are where bricks come from. Nothing we are doing needs a rootfs write.
