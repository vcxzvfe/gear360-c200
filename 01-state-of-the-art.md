# State of the Art — SM-C200 (2016)

Everything the community has established, organised by topic, **with per-model
attribution**. Read the model tag on every line. The two Gear 360 models share a
platform but differ in ways that have destroyed hardware.

---

## 0. Model identity — read this first

| | SM-C200 | SM-R210 |
|---|---|---|
| Year / shape | 2016, spherical | 2017, "lollipop" |
| Photo resolution | 7776×3888 `[VERIFIED]` | 5792×2896 `[VERIFIED]` |
| Video (this project) | 3840×1920 | 4096×2048 |
| Live preview stream | **Yes** (local RVF) `[VERIFIED]` | `[UNKNOWN]` — never documented |
| Samsung "Live Broadcast" (RTMP) | **No** `[COMMUNITY]` | Yes `[COMMUNITY]` |
| Google Street View / OSC mode | **Yes, from launch** `[COMMUNITY]` | Not at launch; added later `[COMMUNITY]` |
| Firmware header project name | `SMC200` `[VERIFIED]` | `SMR210` (inferred by symmetry) |
| Latest firmware | `C200GLU0AQK1` (0.85, 2017-11-21) | `R210GLU0ARB2` |

`[VERIFIED]` Photo resolutions come from the two Hugin templates in
ultramango/gear360pano, which are separate files precisely because the geometry differs:
- https://github.com/ultramango/gear360pano/blob/master/gear360sm-c200.pto
- https://github.com/ultramango/gear360pano/blob/master/gear360sm-r210.pto

**`[VERIFIED]` The model is encoded in the firmware image header in plaintext.** From my
own inspection of `C200GLU0AQK1.bin`, bytes 0x00–0x2B:

```
00000000: 534c 5000 302e 3835 0000 0000 534d 4332  SLP.0.85....SMC2
00000010: 3030 0000 0000 0000 0000 0000 534d 4332  00..........SMC2
00000020: 3030 474c 5530 4151 4b31 0000 0a00 0000  00GLU0AQK1......
```

magic `SLP\0` · version `0.85` · project `SMC200` · build `SMC200GLU0AQK1`.
The literal `SMR210` occurs **zero times** in the whole 279 MB image. You can therefore
verify any `.bin` is C200 before it goes near the camera — see
`03-safety-and-recovery.md`.

---

## 1. Platform

`[VERIFIED]` Both Gear 360 models and the Samsung NX Linux cameras are the same platform
at the shell level:

- ARMv7 Cortex-A9 (`CPU part : 0xc09`), `Hardware : Samsung-DRIMe5-ES`
- Linux 3.5.0, Samsung Linux Platform (SLP), Tizen-derived layout
- Hostname `drime5`; login banner `SAMSUNG LINUX PLATFORM / drime5 login:`
- `/etc/passwd` contains `root::0:0:root:/root:/bin/sh` — **root, no password**

Source (C200 `/proc/cpuinfo`, posted by a confirmed C200 owner):
https://github.com/ultramango/gear360reveng/issues/7

> **Trap.** `[VERIFIED]` The prompt `[root@drime5 ~]#` is shared by the C200, the R210
> *and* the NX1/NX500. A `drime5` prompt in a forum screenshot is **not** evidence of
> which camera you are looking at. Several published attribution errors trace to exactly
> this.

`[VERIFIED]` The NX lineage is visible inside the C200 firmware itself: the embedded
factory help text discusses aperture values, zoom points, lens IDs, backlash and
"AF SET as NX-MINI mode" — none of which a fixed-aperture 360 camera has.

---

## 2. The `info.tg` trigger chain — how code runs as root

This is the foundation of everything.

`[VERIFIED — Samsung's own firmware]` Extracted by me from `C200GLU0AQK1.bin` at
~0x17A07E3:

```
[THE FOLLOWING]: File copy to SD card(root).
  info.tg : Name of file to execute (paf_adj_restore.adj).
  paf_adj_restore.adj : DFMS cmd to restore paf adjust data (paf debug_write 1).
  paf_adjData_backup.txt : Data of PAF adjustment
```

So the mechanism, from the vendor's own documentation:

```
SD card root/
  info.tg        →  contains the NAME of an .adj file to execute
  <name>.adj     →  contains a DFMS command
                    the useful verb is: shell script /mnt/mmc/<script>.sh
  <script>.sh    →  arbitrary shell, runs as root
```

**This settles a question the community left open:** the `.adj` filename is **arbitrary**,
because `info.tg` names it. Samsung's own example is `paf_adj_restore.adj`. Two working
C200 packages use two different names (`nx_cs.adj`, `nx_ft.adj`) and both work.

`[VERIFIED]` NX-side documentation of the same chain (the origin of the technique):
https://github.com/ottokiksmaler/nx500_nx1_modding/blob/master/Running-shell-scripts-from-SD-card.md

`[VERIFIED]` Presence of `info.tg` also starts the `dfmsd` daemon, which on NX overlays a
test UI. `killall dfmsd` restores the normal UI on NX. **`[UNKNOWN]` whether
`killall dfmsd` is safe or necessary on the C200.**

`[VERIFIED]` `dfmsd` (×23) and `dfmstool` (×14) are present as strings in the C200
firmware image, so the daemon and its client both exist on this model.

### Byte-exact trigger files (verified by me with `xxd`)

**Package A — LalaTheDog, firmware flashing.** https://github.com/LalaTheDog/2016Gear360FirmwareUpdate

```
info.tg    11 bytes: 6e78 5f63 732e 6164 6a0a 0a           "nx_cs.adj\n\n"   ← TWO newlines
nx_cs.adj  35 bytes: "shell script /mnt/mmc/upgrader.sh \n"                  ← trailing SPACE
```

**Package B — lansysart, telnet mod.** https://github.com/lansysart/gear360-telnet.usbshell-mod

```
info.tg    18 bytes: "nx_ft.adj\ndfms.tg\n"
nx_ft.adj  31 bytes: "shell script /mnt/mmc/mods.sh \n"                      ← trailing SPACE
dfms.tg     0 bytes  (empty)
```

> **Both `.adj` files carry a trailing space before the newline.** If you retype these by
> hand rather than copying the files, that whitespace and the exact newline count are the
> kind of detail that silently breaks the chain. **Copy the files; do not retype them.**

`[UNKNOWN]` What the empty `dfms.tg` does. It appears in **no** NX documentation, and my
byte search of the C200 firmware found `dfms.tg` **zero** times — though that search
cannot prove absence (payload is compressed). Hypothesis only: it suppresses the test-mode
overlay. Untested.

`[VERIFIED]` `nx_cs.adj` **is** present as a literal string in a readable region of the
C200 firmware (×5), including the full path `/mnt/mmc/nx_cs.adj` adjacent to the tokens
` CS ` and `DEV`. `nx_ft.adj` was not found — but again, **absence in a compressed image
proves nothing**, and `nx_ft.adj` demonstrably works.

---

## 3. Root shell on the C200

`[COMMUNITY — four independent reports, strong]` The chain executes shell as root on the
SM-C200 and **was never patched**, including on the final firmware.

https://github.com/ultramango/gear360reveng/issues/7 — issue title is literally
*"Got Remote Shell in Gear 360 (SM-C200)"*. Confirmations:

- **usumfabricae** — opened the issue, C200 in the title.
- **ultramango** — repo owner; repo is C200-only (only C200 firmware links).
- **teccheck** — asked point-blank *"2016. model?"* → *"Yes"*.
- **KieronQuinn / Quinny899** — never states his model in the issue, but on XDA states
  *"I have a 2016 camera, yes"* and *"I don't have a 2017 Gear 360 and don't plan to get
  one"*. His *"I'm on the latest"* therefore means the last C200 build.

> **Note.** Fetch this thread with `gh api repos/ultramango/gear360reveng/issues/7/comments`.
> The rendered HTML page hides most of the 29 comments.

### The PATH trap `[COMMUNITY — C200, latest firmware]`

> *"It appears in the newer firmware (I'm on the latest) the path no longer contains
> /usr/sbin. The PATH is now: `/usr/share/scripts:/usr/gnu/bin:/usr/local/bin:/bin:/usr/bin:.`"*
> — KieronQuinn

**Consequence: every binary in your script must be called with an absolute path**, or it
fails silently. This is why one C200 owner concluded his camera "didn't have
wpa_supplicant" when it was sitting at `/usr/sbin/wpa_supplicant` all along.

`[VERIFIED]` The working C200 mod scripts defend against this by re-exporting a full PATH
as their first act:

```sh
export PATH="/usr/share/scripts:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:..."
```

### `[UNKNOWN]` — the script filename

One report claims the payload script must be named `test.sh` on the C200. This is almost
certainly wrong: the full path is inside the `.adj` file, and the two working C200
packages use `upgrader.sh` and `mods.sh`. Treat "must be `test.sh`" as folklore.

---

## 4. Persistence and the hibernate snapshot — the danger zone

`[COMMUNITY]` **The C200 does not cold-boot normally. It resumes from a hibernation
snapshot.** Writes to `/` therefore do not survive unless the snapshot is rebuilt, and an
edited rootfs paired with a stale snapshot is *the* documented way to corrupt the device.

> *"the camera always restarts from hibernate and **first attempt to change root
> filesystems resulted in filesystem corruption.**"* — usumfabricae, SM-C200

Corruption signature `[COMMUNITY, C200]`:

```
ls: cannot access factory_check_script.sh: Input/output error
 1710 -?????????  ? ?    ?       ?            ? factory_check_script.sh
```

### The published repair — and its real success rate

`[COMMUNITY]` `/usr/bin/erase_snapshot.sh` then, after reboot, `/usr/bin/make_snapshot.sh`.
Both confirmed to exist in `/usr/bin` on a real C200 (teccheck's screenshot).

**Do not present this as reliable.** Public record:
- teccheck — worked.
- kjuanman — *"not worked for me"* on first attempt; succeeded only via a longer 12-step
  sequence he prefixed *"Warning, Danger: this can brick your camera."*
- rroseirac — C200 in an infinite restart loop, offered only "pull the battery", **never
  recovered**. pensadorxx reported the identical symptom in 2020, also never resolved.

**Roughly one in three attempts in the public record.** Full procedure and its caveats in
`03-safety-and-recovery.md`.

### Persistence hook points

- `[COMMUNITY, C200]` `/usr/lib/systemd/system/factory_check.sh` — used successfully.
- `[COMMUNITY, C200]` `/usr/bin/deviced-pre.sh` — used by the 2026 lansysart mod.
- **`[CORRECTED]`** `/usr/mod/factory_check_script.sh` and `/usr/mod/autostart_script.sh`
  were previously listed as hook points. They are not. They appear in the record only as
  the **symptom** of teccheck's filesystem corruption — unreadable inodes. **Nobody has
  demonstrated using them as hooks on a C200.**

---

## 5. Live video — what is actually established

### 5.1 The stream exists on the C200 `[VERIFIED]`

From the camera's own runtime log. Device identity is airtight:
`msgId[BT_DEVICE_INFO_ID], model_name[SM-C200], model_version[C200GLU0APE4_0.70]`, and
the sibling `Device.xml` reads `<BaseModelName value="SAMSUNG SMC200"/>`.

https://github.com/ultramango/gear360reveng/blob/master/logfiles/CFN003330DC2D53_20160731_120624_a9_dlog.info

Advertised stream URLs (verbatim from the log):

```
<QualityHighUrl>http://192.168.49.10:7679/livestream_high.avi</QualityHighUrl>
<QualityMiddelUrl>http://192.168.49.10:7679/livestream_middle.avi</QualityMiddelUrl>
<QualityLowUrl>http://192…                        ← log truncates here
```

`[UNKNOWN]` The exact low-quality filename. The line is cut off. `livestream_low.avi` is
a **guess**, not evidence. A fourth path, `/livestream_recording.avi`, is used while
recording `[VERIFIED]`.

### 5.2 The GET *is* the start command `[VERIFIED]`

Traced line-by-line in the log; elapsed under 2 ms:

```
GET /livestream_high.avi  →  setStreamingQuality → dlna_set_stream_quality
                             [RVF_STREAMING_HIGH] → start_RVF_streaming(782)
                             → CDSRVF_Mpegfunc_mpeg_start → stop_liveview → LV_STOP
                             → HTTP/1.1 206 Partial Content
```

The client request, byte-for-byte:

```
GET /livestream_high.avi HTTP/1.1
User-Agent: Android Linux
Host: 192.168.49.10:7679
Connection: Keep-Alive
```

`[VERIFIED]` TecCheck's Android app emits this identical string
(`MediaExtractor.java:118`), confirming it was copied from the official app.

### 5.3 The payload is TTTS/HEVC, **not** AVI `[VERIFIED]` ← corrects earlier research

Two independent sources agree, one of them the camera itself:

- Camera log: `Header info : 204 [TTTS] [type : 3] [width : 2560] [height : 1280]
  [bitrate : 22000000]` and `cHalVideoHEVCEncoder.cpp:Configure(237)> HEVC[0] Cfg WH
  2560x1280 30, BR:22000kbps`
- TecCheck's `Extractor.kt`: `TAG_TTTS = 0x54545453`, plus `VID0 / AUD0 / VR00 / LIST /
  MOVI / 00VD / 00AU / 00VR`; codec id `1 -> MimeTypes.VIDEO_H265`
- `[VERIFIED, by me]` The literal `TTTS` appears in the C200 firmware image.

**The `.avi` extension, the `Content-Type: video/x-avi`, and the DLNA profile string
`AVC_MP4_BL_CIF15_AAC_520` are all mislabels.** The DLNA string even advertises AVC/H.264
while the encoder is HEVC. **ffplay/VLC will not open this stream.**

Container layout `[VERIFIED]` from two independent implementations:

```
"TTTS" header (204 bytes) → VID0 / AUD0 / VRO0 sub-headers → LIST/movi
then repeating chunks: tag(4) + size(u32) + timestamp(u64) + payload
  00VD = video (HEVC)
  00AU = audio (AAC)
  00VR = per-frame gyro: yaw / pitch / roll as num/den integer pairs
```

`[INFERRED]` The video chunks appear to be **Annex-B HEVC elementary stream**: the
"keyframe marker" bytes 64 and 38 that the Samsung app checks decode as NAL headers
(`0x40` → nal_unit_type 32 = VPS, `0x26` → type 19 = IDR_W_RADL), which implies each
chunk begins with the start code `00 00 00 01`. If correct, concatenated `00VD` payloads
feed straight into `ffmpeg -f hevc`. **Not yet confirmed on a real capture.**

> `[UNKNOWN]` **The two reference implementations disagree** on whether to strip the first
> 5 bytes of each video chunk. The Java one keeps them; the Kotlin one reports
> `size - 5`. The NAL analysis above says *keep*. Resolve empirically on the first
> capture — this is a 30-second `ffprobe` test, not a research project.

### 5.4 Stream parameters `[VERIFIED]`

| Stream | Resolution | FPS | Bitrate |
|---|---|---|---|
| `livestream_high.avi` | 2560×1280 | 29.97 | 22 Mbit/s |
| `livestream_recording.avi` | 2560×1280 | 59.94 | 30 Mbit/s |
| `livestream_middle.avi` | `[UNKNOWN]` | `[UNKNOWN]` | `[UNKNOWN]` |

`[VERIFIED]` The camera also exposes 9 selectable stream resolutions and 3 quality levels
(`2560x1280, 1920x1920, 1920x1080, 2880x1440, 1440x1440, 1440x860, 1280x1280, 1280x720`).

`[UNKNOWN]` Whether 22 Mbit/s actually sustains over the camera's Wi-Fi. It very likely
does not; the middle/low variants are probably the usable ones. **No measurement exists.**

`[UNKNOWN]` Whether the stream is dual-fisheye side-by-side or something else. The 2:1
aspect at 2560×1280 and the `lensInfo/horiAngle/vertiAngle` fields strongly suggest
side-by-side fisheye `[INFERRED]`, but nobody has looked at a decoded frame.

### 5.5 The control plane `[VERIFIED]`

- UPnP/DLNA control on **TCP 7676**; root description at `/smp_2_`, ContentDirectory
  control at `/smp_4_`. Ports come from the camera's own
  `/mnt/mmc/.config/UPnPConfig.xml`: `<HTTPTCPServerPort>7676</HTTPTCPServerPort>`,
  `<HTTPStreamingPort>7679</HTTPStreamingPort>`.
- **49 SOAP actions** — I re-counted them directly from the camera's own
  `ContentDirectory_1.xml`; the count and order match exactly. Includes `GetInfomation`
  (sic) → returns `StreamUrl`, `SetOperationState`, `SetStreamQuality`, `StopStreaming`,
  `X_PauseStreaming`, `StartRecord`, `StopRecord`, `Shot`, `SetISO`, `SetEV`, `SetWB`,
  `X_SetHDR`, `X_DeleteFile`.
- Entering live view: `SetOperationState` with `StateEvent = changeToRVF`.
- The app speaks **HTTP/1.0** with `Connection: close` on the control channel.

**`[CORRECTED]` The User-Agent ACL.** Earlier research claimed a naive client "will likely
be rejected at the SOAP layer". The log does not support that. All six `CheckAccessControl`
invocations sit on device-**description** requests, and the four rejections all end in
`DescriptionRequestReceived(1014) > 503 ServiceUnavailable`. The SOAP control POSTs to
`/smp_4_` show **no** preceding access check. The rejected agent was the phone's own
generic DLNA probe (`DLNADOC/1.51 SEC_HHP_[Phone]Samsung Galaxy S7/1.0`), and the session
worked fine anyway. **Whether a plain client can drive the SOAP endpoint is `[UNKNOWN]`
and is a five-minute test, not an assumption.**

### 5.6 Bluetooth is only a Wi-Fi power switch `[VERIFIED]`

The BT `liveview` command starts no stream. Timestamps from the log: `[EXE_LIVEVIEW]` at
t=592.867942 → `wifi_direct_activate() SUCCESS` at t=592.871605 — a 3.66 ms gap. The DLNA
servers appear only after the Wi-Fi Direct connection completes.

**Everything after that point is ordinary HTTP and SOAP over Wi-Fi.** This is the reason
to believe a phone-free path may exist.

`[VERIFIED]` The BT message is a `cmd-req` with `{enum:"execute", description:"liveview"}`
on Samsung Accessory Protocol channel 204, profile id `/system/DI_360_2D`.

### 5.7 Addressing `[VERIFIED]`

- **Wi-Fi Direct** (camera as P2P client): camera at `192.168.49.10`. This is what the
  camera log captures.
- **SoftAP** (camera as AP): camera at `192.168.107.1`. Confirmed independently by
  baardove/osc (*"the cameras address is 192.168.107.1"*) and by TecCheck's app, which
  hardcodes `http://192.168.107.1:7679/livestream_high.avi`.
- `[VERIFIED]` Port **7679 is not listening when idle.** An nmap of the camera showed only
  53, 7676, 9001 open. `[INFERRED]` 7679 binds only while RVF is active — this is inferred
  from two non-simultaneous observations, not measured.
- `[VERIFIED]` Port **9001** is a plain HTTP file server rooted at DCIM, for pulling
  recordings. Config: `/mnt/mmc/.config/http_stream.ini` → `HTTPPort=9001`.

---

## 6. The OSC (Open Spherical Camera) side channel

`[COMMUNITY]` The C200 runs a **Google OSC API level 1** HTTP server on its own Wi-Fi AP
in Street View mode. SSID ends in `.OSC`; the 8-digit password is shown on the camera LCD.
Drivable from a PC with plain Python — **no phone, no Samsung app**.

https://github.com/baardove/osc — *"simple python script to take and grab an image from a
spherical camera (Samsung Gear 360 2016)"*

`[COMMUNITY]` Mapillary's developers characterise it as *"semi OSC compliant"*.
`[COMMUNITY]` The camera stitches in-camera in this mode (10–15 s per photo) — slow, and
reportedly cropped, but it is real equirectangular output with no desktop work.

`[INFERRED]` OSC live preview (`camera.getLivePreview`, MJPEG) is documented by Google as
**API level 2+**, so a level-1 camera probably lacks it. **`[UNKNOWN]` — nobody has ever
dumped `/osc/info` from a C200.** This is the cheapest unresolved question in the entire
project: one `curl`, zero risk. See Experiment 3.

`[VERIFIED, by me]` `OSC` appears ×164 and `/osc/` ×1 in the C200 firmware image;
`camera.getLivePreview` and `takePicture` were not found — **but the image is compressed,
so that is not evidence of absence.**

Note the inversion of the usual assumption: `[COMMUNITY]` **the C200 has Street View/OSC
from launch; the R210 did not** and only gained it in a later firmware. On this axis the
2016 model is the *more* capable one.

---

## 7. Firmware versions

`[COMMUNITY]` Six C200 builds are attested: `APC9`, `APE4`, `API1`, `AQC1`, `AQF1`, `AQK1`.
**Only two binaries were ever archived** — `APE4` and `AQK1`.

`[VERIFIED]` Authoritative hashes, from KieronQuinn's archive
(https://github.com/KieronQuinn/Gear360_OSS/tree/main/firmware/SM-C200):

```
C200GLU0AQK1_171121_1257_REV00_user.bin   279,094,189 bytes
  SHA256 150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db
C200GLU0APE4_160519_1848_REV00_user.bin
  SHA256 f0962ca7521d82219a3e2418cc26fc046db39d8c40e428f5528287e1c7e7ebea
```

`[VERIFIED, by me]` The copy in this scratchpad matches the AQK1 hash exactly.

`[VERIFIED]` **Every original Samsung host is dead** — `secaz-wearable-dn.samsungdm.com`,
`www.samsungimaging.com`, `az335309.vo.msecnd.net` all NXDOMAIN. Wayback has no capture of
the `.bin`; archive.org has no item. The only surviving public mirror is an XDA attachment
behind a login. **Guard the copy you have.**

### The unresolved AQK1 conflict `[COMMUNITY — genuinely contradictory]`

Against AQK1:
> *"DONT UPDATE to this version … a) it will not transfer files via USB to PC … and b) it
> will not send live feed to my S8 via the app … it won't do Camera [the viewfinder mode]
> at all."* — quoted on 4PDA

For AQK1:
- Andy2000 (4PDA) flashed a 2016 camera to AQK1: *"Камера снимает, приложение склеивает и
  сохраняет"* (camera shoots, app stitches and saves).
- lansysart's 2026 telnet mod **requires** AQK1.
- LalaTheDog: the Gear VR controller works as a remote shutter **only** on AQK.

**This directly threatens the live-video goal and is unresolved.** You have two units —
this is exactly the experiment two units are for. **Do not flash your working unit to
AQK1 while chasing live video until you have measured the viewfinder on its current
firmware.**

> **Critical caveat nobody stated.** All wire-level protocol evidence (ports, TTTS, RVF,
> the 49 SOAP actions) comes from firmware **`C200GLU0APE4`** — the **oldest** of the six
> builds. Do not assume it survives a flash to AQK1.

---

## 8. Bricking — the empirical record

`[COMMUNITY, strong]` **Flashing R210 firmware onto a C200 is the documented hard-brick
path, with no known recovery.** Two named cases:

- kras891 flashed `R210GLU0ARB2` → *"You flashed a 2017 model firmware on a 2016 model
  device. You've bricked it, sorry. No known solution to that."*
- Drag0nR13: *"I mistakenly flashed the SM-R210 firmware onto my SM-C200 Gear 360 … no
  LEDs, no signs of power, and no USB detection"* → *"As far as is known, there is no
  solution. It's bricked, sorry."*

`[COMMUNITY]` The Russian 4PDA thread carries an all-caps warning, **edited in
specifically** after bricking reports:

> *"Внимание!!! Способ ТОЛЬКО ДЛЯ камеры SM-R210 2017 gear 360!!!!! Если применить к
> 2016го года камере (Круглые С200) у вас будет 100% кирпич."*
> ("Attention!!! Method ONLY FOR the SM-R210 … If applied to the 2016 camera (round C200)
> you will have a 100% brick.")

`[COMMUNITY]` **One credible C200 recovery exists, n=1.** Zet_Zverev (confirmed C200
owner — posted his own `C200GLU0AQK1` firmware string across multiple years) revived a
camera showing `Error` on power-on by SD-flashing the **oldest** firmware first, then the
newest. **Scope it carefully:** the symptom was "Error"/update loop, *not* the dead-hardware
state, and *not* the infinite-restart loop that was never fixed for anyone.

`[VERIFIED]` No hardware recovery exists: no download-mode button combo documented for the
C200, no JTAG/UART annotated in the FCC internal photos, and the official manual documents
**no hardware reset at all** — only an app-driven "Reset and format".

`[COMMUNITY]` `[R210 only — untested on C200]` A DOWNLOAD mode reachable by holding
OK+Menu then Power, enumerating as "Samsung SDB Interface", is reported **for the R210
only**, by a reporter who explicitly wrote "YMMV". **No one has confirmed it on a C200.**
Trying it is an experiment, not a step.

---

## 9. Desktop / stitching tooling (reuse, don't rebuild)

| Tool | Model | Licence | Note |
|---|---|---|---|
| ultramango/gear360pano | C200 + R210 templates | MIT | Hugin `.pto` with real optimised C200 geometry. **Abandoned since 2018-07-09.** |
| drNoob13/fisheyeStitcher | **C200 only** | MIT | *"Model supported: Samsung Gear360-C200 (195-degree FOV)"*; ships the 28 MB MLS grid in-repo |
| bilde2910/stitch-gear360 | **C200 only** | MIT | Wrapper; injects Google spatial-media metadata; hard-rejects non-3840×1920 |

`[VERIFIED]` gear360pano dispatches on `exiftool -Model` matching literal `SM-C200` /
`SM-R210` — a reusable model-detection convention. **Caution:** its *video* templates are
selected by **resolution**, not model.

`[INFERRED — measured during research, not from any source]` For quick ffmpeg-only
conversion of C200 3840×1920 footage, the seam-minimising parameter is **191°**, not the
nominal 195° and not 180°:

```
ffmpeg -i IN.mp4 -vf "v360=dfisheye:e:ih_fov=191:iv_fov=191" -c:a copy OUT.mp4
```

A residual seam always remains, because `v360` has no per-lens roll/pitch correction —
which is precisely what the Hugin `.pto` r/p/y terms encode. Use `v360` for speed, Hugin
or fisheyeStitcher for quality.

`[COMMUNITY]` macOS 2026: Homebrew's `hugin` cask was **disabled 2025-11-10**. Use the
arm64 Hugin 2024.0.1 DMG from dannephoto, or MacPorts `hugin-app`. ffmpeg arm64 works
natively.

---

## 10. What nobody has done yet

This is the honest frontier. Do not assume any of these are "almost done".

1. **Pulled the live stream onto a PC/Mac.** Ever. By anyone. The only consumers in
   existence are the official Samsung Android app and TecCheck's app — whose author says:
   *"I'm sorry, but I lost interest in the project. I wouldn't recommend trying it out."*
2. **Triggered RVF mode without an Android phone.** The whole phone-free path is
   unproven.
3. **Dumped `/osc/info` from a C200.** One curl. Nobody has run it.
4. **Started the stream from a camera-side root shell.** `[COMMUNITY]` Everything lives in
   one monolithic `di-camera-app`; no CLI verb was ever found, and `st app nx capture
   single` **reboots** the C200.
5. **Measured the real throughput or latency** of any C200 stream quality.
6. **Looked at a decoded frame** — so fisheye vs stitched vs something else is unknown.
7. **Written a TTTS demuxer for desktop.** The spec is known; the code is not written.
8. **Resolved the AQK1 viewfinder conflict.**
9. **Recovered a hard-bricked C200.** No one, ever.
10. **Found the C200's `capdtm` user-data table.** Nobody has published
    `st cap capdtm usrlist` output from a C200. **`[CORRECTED]`** The circulating table is
    the R210's.

### Techniques that do NOT transfer — do not attempt blind

- `[VERIFIED]` **mewlips/nx-remote-controller-mod** (`/dev/mem` framebuffer scrape). It
  `die("unsupported nx model.")`s on anything outside {NX1, NX300, NX300M, NX2000, NX3000,
  NX500}, and its physical addresses are per-model hardcoded tables with **no Gear 360
  entry**. Moreover the C200 has no live-view LCD, so the buffer it scrapes may not exist.
- `[VERIFIED]` **The NX `bluetoothd` patch** for escaping factory mode. It **corrupts the
  C200 root filesystem** because the C200 boots from a hibernate snapshot.
- `[VERIFIED]` **`keyscan360` button triggering.** NX/R210 code; its own header says
  *"capture keypresses on NX500/NX1"*; the one C200 attempt failed and the author
  disabled it.
- `[COMMUNITY]` **Every "Gear 360 as webcam" recipe on the internet is R210-only** —
  they capture ActionDirector's Live Broadcast window in OBS, or point OBS at a local
  RTMP server the *phone* pushes to. None applies to a C200.

---

## Source index

| What | URL |
|---|---|
| C200 reverse engineering + the device log | https://github.com/ultramango/gear360reveng |
| C200 root shell thread (use `gh api …/issues/7/comments`) | https://github.com/ultramango/gear360reveng/issues/7 |
| C200 telnet mod, 2026 | https://github.com/lansysart/gear360-telnet.usbshell-mod |
| C200 SD firmware flash | https://github.com/LalaTheDog/2016Gear360FirmwareUpdate |
| C200 firmware hashes / OSS | https://github.com/KieronQuinn/Gear360_OSS |
| TTTS demuxer reference (Android) | https://github.com/TecCheck/Gear360App |
| C200 OSC client | https://github.com/baardove/osc |
| C200 stitching templates | https://github.com/ultramango/gear360pano |
| C200 stitcher | https://github.com/drNoob13/fisheyeStitcher |
| **R210 (2017) modding — NOT C200** | https://github.com/ottokiksmaler/gear360_modding |
| **R210 (2017) mods — NOT C200** | https://github.com/vitorio/gear360-2017-mods |
| NX origin of the technique | https://github.com/ottokiksmaler/nx500_nx1_modding |
| NX livestream notes | https://github.com/ge0rg/samsung-nx-hacks/wiki |
