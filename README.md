# gear360-c200

Research notes and working procedures for the **Samsung Gear 360 (2016), model SM-C200** —
the spherical one.

**Goal:** get live video out of an SM-C200 and onto a desktop computer, without the
Samsung Android app.

**Status: research. Largely unproven. Nothing here has been validated end-to-end on
hardware by this repository's author.**

---

## ⚠️ Read before you touch hardware

**The SM-C200 has no hardware recovery mode.** No download-mode button combination is
documented for it, no JTAG or UART is documented, and the official manual describes no
hardware reset at all. Every known recovery path requires the camera to still boot Linux
far enough to mount the SD card. **If it stops booting, there is currently no published
way back.**

Three rules, in order of how much damage breaking them causes:

1. **Never put SM-R210 (2017) firmware — or any R210 file — on an SM-C200.** This is the
   documented hard-brick path. Multiple cameras have died this way and **none has ever
   been recovered.** Most R210 material on the internet is not labelled as R210. Verify
   the model attribution of everything.
2. **Never write to the root filesystem until you have exhausted the SD-card-only path.**
   The C200 resumes from a hibernation snapshot rather than cold-booting; an edited rootfs
   paired with a stale snapshot is how every documented C200 filesystem brick happened.
   The published repair works roughly **one time in three**.
3. **Obtain and hash-verify the C200 firmware image before you start.** Every original
   Samsung download host is now dead (NXDOMAIN). If you lose your copy you may be unable
   to obtain another.

Full detail: [`03-safety-and-recovery.md`](03-safety-and-recovery.md). Read it first.

**This repository documents procedures that can permanently destroy hardware. It is
offered as research notes, with no warranty of any kind. You are responsible for your own
equipment.**

---

## Hardware targeted

**SM-C200 (2016) only.**

This repository is deliberately strict about model attribution, because model confusion in
this community is a documented cause of dead hardware. The 2017 SM-R210 is a **different
device with different firmware**, and findings do not automatically transfer in either
direction.

|  | SM-C200 (this repo) | SM-R210 (not this repo) |
|---|---|---|
| Year / shape | 2016, spherical | 2017, "lollipop" |
| Photo | 7776×3888 | 5792×2896 |
| Video | 3840×1920 | 4096×2048 |
| Local live preview | Yes | Undocumented |
| Samsung Live Broadcast (RTMP) | **No** | Yes |
| Street View / OSC | Yes, from launch | Added later |
| Latest firmware | `C200GLU0AQK1` | `R210GLU0ARB2` |

Every claim in this repository carries a model tag and a confidence tag:

| Tag | Meaning |
|---|---|
| `[VERIFIED]` | Primary source, checked byte-level or verbatim |
| `[COMMUNITY]` | Forum / issue report; testimony, not independently reproduced |
| `[INFERRED]` | Reasoning from evidence; explicitly not observed |
| `[UNKNOWN]` | Not established. Not a guess opportunity. |

Where only R210 data exists, it is labelled **"R210 only — untested on C200"** and porting
it is treated as an experiment, never a step.

---

## What is actually known

**The camera already streams live video.** Stock firmware, no root required. It serves
HEVC over plain HTTP on TCP **7679**, proven at the wire level by the camera's own runtime
log from a device that self-identifies as `model_name[SM-C200]`.

**The payload is not what it claims to be.** Despite the `.avi` filename, the
`Content-Type: video/x-avi` header and a DLNA profile string advertising AVC/H.264, the
stream is a Samsung **TTTS** container carrying **HEVC**. No off-the-shelf player opens it.
A demuxer must be written. `ffplay` will not work — this repository exists partly to stop
people losing a weekend to that.

**Root shell on the C200 is a solved problem**, via the Samsung NX-lineage `info.tg`
SD-card mechanism, and it is fully reversible as long as you never touch the root
filesystem.

**Nobody has ever pulled the live stream onto a PC.** That is the open problem.

---

## What nobody has done yet

Stated plainly, so nothing here reads as further along than it is:

- Pulled the live stream onto a PC or Mac. Ever. By anyone.
- Triggered remote-viewfinder mode without an Android phone.
- Dumped `/osc/info` from a C200 (one `curl`; nobody has run it).
- Started the stream from a camera-side root shell (no CLI verb has ever been found).
- Measured real throughput or latency of any C200 stream quality.
- Looked at a decoded frame — so fisheye vs. stitched is genuinely unknown.
- Written a TTTS demuxer for desktop.
- Recovered a hard-bricked C200.

---

## Contents

| File | What it is |
|---|---|
| [`00-executive-summary.md`](00-executive-summary.md) | Verdict, what is achievable, what changed vs. naive expectations |
| [`01-state-of-the-art.md`](01-state-of-the-art.md) | Everything the community established, per-model, with sources |
| [`02-c200-shell-procedure.md`](02-c200-shell-procedure.md) | Rooting: non-persistent path first, persistent path separately |
| [`03-safety-and-recovery.md`](03-safety-and-recovery.md) | **Read first.** Pre-flight, runbook, one-way doors |
| [`04-live-video-paths.md`](04-live-video-paths.md) | Ranked candidate paths, with falsification tests |
| [`05-experiment-plan.md`](05-experiment-plan.md) | Ordered bench experiments; all observation before any write |
| [`06-open-questions.md`](06-open-questions.md) | Everything still unknown, ranked by how much it blocks |
| [`07-observations.md`](07-observations.md) | **Measurements from real hardware.** Firmware-dependent menus, first published /osc/info, mode-dependent ports |
| [`firmware/CHECKSUMS.md`](firmware/CHECKSUMS.md) | Verification data for the C200 firmware image. No binary is distributed. |
| [`tools/ttts.py`](tools/ttts.py) | TTTS demuxer library, written from the camera's own muxer. 19 tests, incl. real-HEVC round trip |
| [`tools/ttts_capture.py`](tools/ttts_capture.py) | CLI: capture from the camera, or re-demux a saved container |
| [`tools/osc_probe.py`](tools/osc_probe.py) | Sends OSC commands and reads the errors. Closed the OSC question |
| [`08-firmware-teardown.md`](08-firmware-teardown.md) | **Firmware teardown.** RVF chain, recovered SOAP request, custom-firmware verdict |
| [`tools/c200_fov_calibrate.py`](tools/c200_fov_calibrate.py) | Measures the correct `v360=dfisheye` FOV for a given C200 unit |

---

## Credits — prior art

**Almost everything in this repository is inherited.** This work would not exist without:

- **[ultramango/gear360reveng](https://github.com/ultramango/gear360reveng)** — the
  foundational SM-C200 reverse-engineering repository, and the source of the device log
  that proves the live-stream stack on real C200 hardware. The single most valuable
  artifact in this space.
- **[ottokiksmaler/nx500_nx1_modding](https://github.com/ottokiksmaler/nx500_nx1_modding)**
  and **[ottokiksmaler/gear360_modding](https://github.com/ottokiksmaler/gear360_modding)**
  — origin of the `info.tg` / `.adj` / shell-script technique on the Samsung NX cameras,
  and the Gear 360 (2017) modding work that follows from it. *The gear360_modding
  repository is SM-R210 (2017); it is cited here as lineage, not as C200 procedure.*
- **[TecCheck/Gear360App](https://github.com/TecCheck/Gear360App)** — the only open TTTS
  container implementation in existence, and the only open Bluetooth protocol work. Two
  independent implementations (`MediaExtractor.java`, `Extractor.kt`) are what make a
  desktop demuxer tractable at all.
- **[KieronQuinn/Gear360_OSS](https://github.com/KieronQuinn/Gear360_OSS)** — archived the
  C200 firmware hashes and Samsung's open-source release. Because every Samsung host is
  now dead, this archive is the reason firmware verification is still possible.
  KieronQuinn (Quinny899) also did much of the original C200 shell work and maintained the
  modded Gear 360 Manager.
- **[vitorio/gear360-2017-mods](https://github.com/vitorio/gear360-2017-mods)** —
  well-documented SD-card mod packaging. *SM-R210 (2017).*
- **[LalaTheDog/2016Gear360FirmwareUpdate](https://github.com/LalaTheDog/2016Gear360FirmwareUpdate)**
  — the best C200-vs-R210 differential document in the corpus, and the only byte-verified
  C200 SD firmware-flash file set.
- **[lansysart/gear360-telnet.usbshell-mod](https://github.com/lansysart/gear360-telnet.usbshell-mod)**
  — 2026 C200 telnet-in-normal-boot work.
- **[mewlips/nx-remote-controller-mod](https://github.com/mewlips/nx-remote-controller-mod)**
  — NX live-view daemon. *Does not run on either Gear 360; documented here as a ruled-out
  path.*
- **[ge0rg/samsung-nx-hacks](https://github.com/ge0rg/samsung-nx-hacks)** — SLP firmware
  format and NX livestream documentation.
- **[baardove/osc](https://github.com/baardove/osc)** — plain-Python OSC client for the
  2016 Gear 360.
- **[drNoob13/fisheyeStitcher](https://github.com/drNoob13/fisheyeStitcher)** (MIT) and
  **[ultramango/gear360pano](https://github.com/ultramango/gear360pano)** (MIT) — C200
  stitching.
- The **XDA** Gear 360 Manager thread and the **4PDA** Russian-language Gear 360 thread,
  which between them hold most of the field's brick-and-recovery evidence.

Also to the people whose cameras died producing the warnings in
`03-safety-and-recovery.md`. Those reports are the most useful content in this repository.

---

## What is original here

Modest, and worth stating precisely so it is not mistaken for more.

1. **Model-attribution audit of the existing corpus.** Several widely-circulated "C200"
   claims are R210 findings. Documented, corrected, and traced to source — including a
   published "C200 settings table" that is actually the R210's and contains at least one
   field that exists in no source anywhere.
2. **Correction of the stream-format claim.** The reading that the HTTP 206 +
   `video/x-avi` response makes the NX `ffplay` workaround applicable is wrong. The same
   log shows a TTTS container and an HEVC encoder.
3. **Correction of "the C200 cannot livestream."** The widely-quoted line refers to
   Samsung *Live Broadcast* (RTMP publishing), not the local viewfinder.
4. **A previously unreported hazard in the C200 mod scripts:** `G360POWE_G360POW.sh`
   contains `st cap capdtm setusr` commands copy-pasted from the NX/R210 documentation —
   identifiable by comments listing camera modes a Gear 360 does not have — which write
   factory user-data using another camera's ID table.
5. **Firmware-level evidence.** Direct inspection of `C200GLU0AQK1.bin`: the SLP header
   carries `project = SMC200` in plaintext at offset 0x0C, giving anyone a five-second
   pre-flash model check. Samsung's own factory documentation, embedded in the image,
   settles the long-open question of whether the `.adj` filename matters:

   > `info.tg : Name of file to execute (paf_adj_restore.adj).`

   It does not — `info.tg` names it, and Samsung's own example uses a third name.
6. **An ordered experiment plan that puts all reconnaissance before any write**, based on
   the observation that the live stream is served by stock firmware and therefore needs no
   rooting to investigate.

Everything else is inherited, and cited.

---

## Licence

**Recommendation: MIT for the original content of this repository**, which is consistent
with the surrounding ecosystem (`gear360pano`, `fisheyeStitcher`, `stitch-gear360` are all
MIT).

Three caveats to settle before publishing:

- **Do not commit Samsung firmware binaries.** `C200GLU0AQK1_171121_1257_REV00_user.bin`
  is 266 MiB of Samsung-copyrighted material. Publish the **SHA256 and byte size** so
  others can verify their own copy; do not redistribute the file.
- **Vendored third-party code keeps its own licence.** If any busybox build, `st` binary,
  or code derived from the repositories above is included, carry its licence and
  attribution with it.

  **Several key upstream repositories have no LICENSE file at all** (verified against the
  GitHub API): `TecCheck/Gear360App`, `ultramango/gear360reveng`,
  `lansysart/gear360-telnet.usbshell-mod`, `LalaTheDog/2016Gear360FirmwareUpdate`. With no
  licence, default copyright applies and **their code and files cannot simply be copied
  into an MIT-licensed repository.** In particular `TecCheck/Gear360App` is the most useful
  TTTS reference in existence — **reimplement from the documented format rather than
  lifting source.** For the small trigger files, prefer documenting their exact bytes
  (as this dossier does) over redistributing them, or ask the authors for a licence grant.

  `ultramango/gear360pano` and `drNoob13/fisheyeStitcher` **are** MIT and can be vendored
  with attribution.
- **Quoted forum material** is quoted for identification and safety under fair use; keep
  quotes short and always attributed with a link.

---

## Contributing

The most valuable contributions are **negative results and exact observations**:

- The output of `curl http://192.168.107.1/osc/info` from a C200. Nobody has published one.
- An `ls -l /dev` from a C200. Nobody has published one.
- The contents of `/usr/bin/erase_snapshot.sh` and `make_snapshot.sh`.
- Any measurement of real stream throughput or latency.
- A decoded frame, settling whether the stream is dual-fisheye.

Please state your **model** and **firmware version** in every report. A `[root@drime5]#`
prompt does not identify the model — the C200, the R210 and the NX1/NX500 all share it,
and that ambiguity is the source of most of the corrections in this repository.
