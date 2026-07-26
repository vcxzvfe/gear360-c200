# Executive Summary — Samsung Gear 360 (2016, SM-C200) live-video project

**Target hardware: SM-C200 (2016, spherical). NOT SM-R210 (2017).**
Every claim below carries a model attribution and a confidence tag.

Confidence tags used throughout this dossier:

| Tag | Meaning |
|---|---|
| `[VERIFIED]` | Primary source, checked byte-level or verbatim, model attribution confirmed |
| `[COMMUNITY]` | Forum / GitHub issue report; human testimony, not independently reproduced |
| `[INFERRED]` | Reasoning from evidence; explicitly not observed |
| `[UNKNOWN]` | Not established by any source found. Not a guess opportunity. |

---

## Verdict

**Viable, with one hard reframing: the C200 already streams live video. Nobody has
ever pulled that stream onto a PC. That — not "add streaming to the camera" — is the
actual open problem, and it is a software problem on the *client* side.**

The project is **promising** for the research goal ("get live video out of an SM-C200
onto a Mac"). It is **poor** for the naive goal ("use it as a USB webcam"), which is
blocked by firmware-level constraints that cannot be patched around from userspace.

Three findings drive the verdict:

1. **The stream exists and is proven on real C200 hardware.** `[VERIFIED]` The camera's
   own runtime log — from a device that self-identifies as `model_name[SM-C200],
   model_version[C200GLU0APE4_0.70]` — shows it serving `GET /livestream_high.avi
   HTTP/1.1` on TCP **7679** and answering `HTTP/1.1 206 Partial Content`. This is stock
   firmware behaviour. **No root required.**

2. **Root shell on the C200 is a solved problem.** `[COMMUNITY, strong]` Independently
   reproduced by at least four people, on the latest firmware, via the NX-lineage
   `info.tg` SD-card mechanism. It is reversible if you never touch the root filesystem.

3. **The blocker is the client, not the camera.** `[VERIFIED]` The stream is *not* AVI
   despite the `.avi` name and `video/x-avi` MIME. It is a Samsung **TTTS** container
   carrying **HEVC**. No off-the-shelf player opens it. A demuxer must be written — but
   the format is fully documented by two independent implementations, so this is
   ordinary work, not reverse engineering.

### The single biggest unknown

**Can the camera be driven into Remote-View-Finder (RVF) mode without the Samsung
Android app?** `[UNKNOWN]`

Everything hinges on this. In every captured session the sequence is: phone pairs over
Bluetooth → sends a `liveview` command → camera turns its Wi-Fi on → phone issues SOAP
`SetOperationState(changeToRVF)` → phone GETs the stream. It is unknown whether a plain
laptop can skip straight to the SOAP call (or even to the bare HTTP GET). If it can, the
project is largely a weekend of client-side coding. If it cannot, you need either a
working Android phone in the loop permanently, or camera-side RVF triggering that
**nobody has ever found**.

Good news: this is cheap and **zero-risk** to test. It requires no modification to the
camera at all. See `05-experiment-plan.md`, Experiments 1–4.

---

## What is realistically achievable

| Goal | Verdict | Basis |
|---|---|---|
| Root shell, non-persistent, fully reversible | **Yes** | `[COMMUNITY, 4 independent reports]` |
| Pull recorded files off over Wi-Fi (HTTP :9001) | **Yes** | `[VERIFIED]` in camera log + nmap |
| Receive the live HEVC stream on a Mac | **Likely** | `[INFERRED]` — all pieces exist, never assembled |
| Decode/stitch it to a usable 360 image | **Likely, with work** | `[VERIFIED]` container spec + MIT stitchers exist |
| Trigger the stream without an Android phone | **Unknown — the crux** | `[UNKNOWN]` |
| Persistent root surviving reboot | **Yes, but risky** | `[COMMUNITY, single author, unreplicated]` |
| Indefinite USB-powered operation | **No — firmware blocked** | `[VERIFIED]` official manual |
| USB webcam (UVC device over the cable) | **No** | `[COMMUNITY]`, no USB video path exists |
| Samsung "Live Broadcast" (RTMP to YouTube) | **No — R210 only** | `[COMMUNITY]` |

### Hard limits you cannot engineer around

- **No charging while streaming.** `[VERIFIED]` The official SM-C200 manual states
  verbatim: *"You cannot charge the Samsung Gear 360 while recording a video, using the
  time lapse feature, or using the viewfinder remotely on the connected mobile device."*
  A permanently-powered 360 webcam is therefore **off the table**. You run on the
  internal battery whenever the stream is live.
- **Thermal shutdown.** `[VERIFIED]` Manual: *"If the temperature rises above a certain
  level, the Samsung Gear 360 will stop recording and turn off automatically."*
  `[COMMUNITY]` Real-world figures cluster around 40 minutes, sometimes as little as
  10–20. Forced air cooling helps dramatically.
- **Dual-fisheye, not stitched.** `[INFERRED]` The live stream is 2560×1280 side-by-side
  fisheye. Stitching is your problem, on the Mac, in real time if you want it live.

---

## What changed vs. naive expectations

This section exists because the adversarial verification pass overturned several things
that "everybody knows". **Where verification contradicted the initial research, the
verification wins, and it is called out explicitly here and at every point of use.**

**1. "The C200 can't livestream." — WRONG, and this nearly killed the project.**
The widely-quoted line from Quinny899 (author of the modded Gear 360 Manager) —
*"the livestream requires a 2017 Gear 360"* — refers to Samsung **Live Broadcast**
(publishing to YouTube/Facebook), not the local viewfinder. The same author writes of
his own 2016 camera: *"works just fine on my 2016 camera (live view, videos and photos
all work)."* `[VERIFIED]` **The C200 does serve a local live preview stream.** Taking
the quote at face value would have ended the project on a false premise.

**2. "It's an AVI, just point ffplay at it." — WRONG.**
Initial research concluded the HTTP 206 + `Content-Type: video/x-avi` response meant the
NX-community `ffplay` workaround transfers directly. It does not. The same camera log
shows `Header info : 204 [TTTS] ... [bitrate : 22000000]` and
`cHalVideoHEVCEncoder.cpp:Configure(237)> HEVC[0] Cfg WH 2560x1280 30`. `[VERIFIED]`
The `.avi` extension, the `video/x-avi` MIME, and the `DLNA.ORG_PN=AVC_MP4_...` profile
string are **all three stale mislabels**. Do not budget time for an ffplay pipeline.

**3. The published C200 `capdtm` settings table is actually an R210 table — with at
least one fabricated field.** `[VERIFIED]` The `LENS_MODE_360` / `TIMELAPSESIZE_UD_360`
table attributed to the C200 does not exist in the cited C200 log; repo-wide,
`grep -c "capdtm\|USERDATA_"` over gear360reveng returns **zero**. The real table lives
in ottokiksmaler's repo, whose first README line is *"Repository for Samsung Gear 360
(2017) modding"*. The quoted value `TIMELAPSESIZE_UD_360` appears in **no source
anywhere**; the real R210 line reads `TIMELAPSESIZE_DUAL_2560`.

**4. NEW HAZARD found during this verification, not present in any prior write-up.**
`[VERIFIED]` The C200 mod package `G360POWE_G360POW.sh` (lansysart, and its copies)
contains a block of `st cap capdtm setusr` commands **copy-pasted from the NX/R210
documentation**, complete with NX-only comments listing camera modes
`aperture / shutter / manual / imode / magic / scene` — modes a Gear 360 does not have.
I traced the identical text to `gear360_modding/README.md` (R210) and
`nx500_nx1_modding/ST Commands.md` (NX). **These lines write factory user-data on your
C200 using IDs derived from a different camera's table.** Do not run that script
unmodified. Detail in `03-safety-and-recovery.md`.

**5. The button-press trigger (`keyscan360`) does not work on the C200.**
Prior research labelled it "both models". It is NX/R210 code — its own header comment
reads *"Simple C code to capture keypresses on NX500/NX1"* — and the one person who
tried it on a C200 reported it did not work and removed it. `[VERIFIED]` Do not plan a
C200 workflow around pressing a button.

**6. You are in a much stronger position than the community was.**
`[VERIFIED, by me]` The scratchpad already contains
`C200GLU0AQK1.bin`, 279,094,189 bytes, SHA256
`150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db` — an exact match for
KieronQuinn's archived hash. Every original Samsung download host is now dead (NXDOMAIN).
**You have the recovery image and two units.** That is the difference between "risky" and
"manageable".

---

## Original findings from this dossier's own verification

These were produced by direct inspection of the firmware image, not taken from any prior
write-up. Full detail in `01-state-of-the-art.md`.

- **`[VERIFIED]` The firmware image carries its model identity in a plaintext header.**
  Offsets 0x00–0x2B of `C200GLU0AQK1.bin`: magic `SLP\0`, version `0.85`, project name
  `SMC200`, build `SMC200GLU0AQK1`. The string `SMR210` occurs **zero** times in the
  entire 279 MB image. C200 and R210 images are trivially distinguishable — which is
  exactly why cross-flashing is catastrophic and why you can self-check a `.bin` before
  it ever touches the camera.

- **`[VERIFIED]` Samsung's own factory documentation is embedded in the C200 firmware,
  and it settles the `.adj` naming question.** Extracted verbatim from offset ~0x17A07E3:

  ```
  [THE FOLLOWING]: File copy to SD card(root).
    info.tg : Name of file to execute (paf_adj_restore.adj).
    paf_adj_restore.adj : DFMS cmd to restore paf adjust data (paf debug_write 1).
    paf_adjData_backup.txt : Data of PAF adjustment
  ```

  This is from-the-device proof that **`info.tg` contains the name of the file to
  execute**, and that the named `.adj` file contains a **DFMS command**. The `.adj`
  filename is **arbitrary** — Samsung's own example uses `paf_adj_restore.adj`, which is
  neither `nx_cs.adj` nor `nx_ft.adj`. This resolves an open question that the community
  never settled.

- **`[VERIFIED]` The RVF/DFMS/TTTS stack is present in the C200 firmware image itself.**
  Direct byte search of the 279 MB image: `RVF` ×285, `dfmsd` ×23, `dfmstool` ×14,
  `TTTS` ×2, `ttyGS0` ×15, `funcs_fconf` ×4, `OSC` ×164, `capdtm` ×17, `erase_snapshot`
  ×22, `/mnt/mmc/nx_cs.adj` ×1. Independent C200-side corroboration of claims that
  previously rested only on a device log and on Android app source.

- **`[VERIFIED]` Important epistemic caveat on that search.** The firmware payload is
  **compressed** (measured entropy 6.99–7.96 bits/byte across the image). Known-present
  strings such as `fw_upgrade_start` and `make_snapshot` return **zero** hits. Therefore
  **a zero-hit result in that image is not evidence of absence.** Positive hits are
  evidence; negative hits are not. Stated here so nobody later cites my own search as
  proof that something is missing.

---

## Recommended posture

1. **Do all live-video reconnaissance on a bone-stock camera first.** The stream is
   served by stock firmware. Root is only needed to trigger it *without a phone* — which
   is a later question. This inverts the obvious plan and removes essentially all risk
   from the first phase.
2. **Designate one unit as the guinea pig and keep the second sealed.** Do not modify
   both. The second unit is your known-good reference and your comparison for "is this
   behaviour normal?"
3. **Never write to the root filesystem until the non-persistent path has answered every
   question it can.** Rootfs writes are where every documented C200 brick came from.
4. **Never put an R210 file of any kind on a C200.**

---

*Continue to `03-safety-and-recovery.md` before touching hardware, then
`05-experiment-plan.md` for the ordered bench sequence.*
