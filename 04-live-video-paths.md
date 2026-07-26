# Live Video — Ranked Candidate Paths

**This is the unsolved part of the project.**

`[COMMUNITY]` Nobody has ever pulled live video off an SM-C200 onto a PC. The only
consumers that exist are the official Samsung Android app and TecCheck's Android app,
whose author wrote in 2024: *"I'm sorry, but I lost interest in the project. I wouldn't
recommend trying it out."*

Everything below is a **hypothesis with an evidence trail**, not a recipe.

Effort figures assume agent-assisted work with parallel investigation, not solo
hand-coding.

---

## The one reframing that matters

**The camera already streams live HEVC video over HTTP. Stock. No root required.**

The problem is not "make the camera stream." The problem is:

1. **Trigger** — get the camera into Remote-View-Finder mode without the Samsung app.
   `[UNKNOWN]` — the crux.
2. **Transport** — reach TCP 7679. `[VERIFIED]` — trivially solved once triggered.
3. **Decode** — the payload is a Samsung TTTS container, not AVI. `[VERIFIED]` — needs a
   demuxer, but the format is fully documented.

Paths are ranked by (probability × value) ÷ effort.

---

# Path 1 — Drive the stock RVF stack from the Mac ★ RECOMMENDED

**Hypothesis:** join the camera's own Wi-Fi, issue the same SOAP/HTTP the Samsung app
issues, receive TTTS/HEVC, demux it locally.

### Evidence FOR

- `[VERIFIED]` The camera serves `GET /livestream_high.avi HTTP/1.1` on **TCP 7679** and
  answers `HTTP/1.1 206 Partial Content`. Proven on real C200 hardware
  (`model_name[SM-C200]`).
- `[VERIFIED]` **The GET itself is the start command.** Under 2 ms after the request the
  camera runs `start_RVF_streaming` and `LV_STOP`. There is no separate "begin" call.
- `[VERIFIED]` Ports come from the camera's own config file, not guesswork:
  `<HTTPTCPServerPort>7676</HTTPTCPServerPort>`, `<HTTPStreamingPort>7679</HTTPStreamingPort>`.
- `[VERIFIED]` The full control surface is documented — **49 SOAP actions** in the
  camera's own `ContentDirectory_1.xml`, including `SetOperationState(changeToRVF)`,
  `GetInfomation` → `StreamUrl`, `SetStreamQuality`.
- `[VERIFIED]` **Bluetooth is only a Wi-Fi power switch.** `[EXE_LIVEVIEW]` →
  `wifi_direct_activate() SUCCESS` in 3.66 ms; no stream is started. Everything after is
  ordinary HTTP/SOAP. **This is the reason to believe a phone-free path exists.**
- `[VERIFIED]` The container format is fully specified by two independent implementations
  (TecCheck's `MediaExtractor.java` and `Extractor.kt`).
- `[VERIFIED]` SoftAP address `192.168.107.1` is independently corroborated by two
  unrelated projects.

### Evidence AGAINST

- `[UNKNOWN]` **Nobody has ever done it.** That is not evidence it fails, but it is not
  nothing either — several capable people looked.
- `[VERIFIED]` A User-Agent ACL exists (`PATTERN SEC_RVF_ML_`). **`[CORRECTED]`** Earlier
  research claimed this blocks SOAP. The log does not support that: all six access checks
  sit on device-*description* requests, and the SOAP POSTs to `/smp_4_` show no check at
  all. Still, it is a real filter and may bite.
- `[VERIFIED]` Port 7679 is **not listening when idle** — an nmap showed only 53, 7676,
  9001. `[INFERRED]` it binds only while RVF is active. So a bare GET may hit a closed
  port until something puts the camera into RVF.
- `[UNKNOWN]` Whether the camera will enter RVF mode at all without a paired BT device.

### Sub-paths, easiest first

**1a — Phone-in-the-loop (highest probability, lowest elegance).**
Use the Android app to get the camera into live view, then join the same network from the
Mac and issue the GET yourself. This sidesteps the entire trigger question and tests the
transport and decode layers independently. **Do this first** — it decomposes the problem.

**1b — Fully phone-free via SoftAP.**
Put the camera in its own AP mode (Street View / Wi-Fi mode on the camera body), join from
the Mac, probe 7676/7679. If 7679 answers without any Bluetooth at all, the whole
dependency collapses.

**1c — Phone-free via SOAP.**
If the bare GET fails, replay `SetOperationState(changeToRVF)` then `GetInfomation`
against `/smp_4_` on 7676, spoofing `User-Agent: SEC_RVF_ML_<mac>` if needed.

### Effort
- Transport probing: **~1 hour**, zero risk.
- TTTS demuxer: **~2–4 hours.** The format is documented; this is ordinary parsing work.
  `[UNKNOWN]` one open detail — the two reference implementations disagree on whether to
  strip 5 bytes per video chunk. `[INFERRED]` from NAL analysis: **keep them**. Settle it
  with one `ffprobe`.

### Fastest falsification
Join the camera's Wi-Fi and run:

```bash
nmap -Pn -p 53,7676,7679,9001 192.168.107.1
curl -v --http1.1 -A 'Android Linux' \
     http://192.168.107.1:7679/livestream_high.avi -o /tmp/out.ttts
```

If 7679 is closed with the camera in every mode you can put it in, and no SOAP call opens
it, Path 1b/1c is dead and you fall back to 1a. **Cost: 15 minutes, zero risk.**

---

# Path 2 — OSC API probe ★ CHEAPEST TEST, DO IT FIRST

**Hypothesis:** the C200's Open Spherical Camera server exposes something useful, possibly
including live preview.

### Evidence FOR
- `[COMMUNITY]` The C200 runs an **OSC API level 1** HTTP server on its own AP in Street
  View mode, drivable from a PC with plain Python, **no phone and no Samsung app**
  (baardove/osc).
- `[COMMUNITY]` Mapillary developers independently confirm it: *"semi OSC compliant."*
- `[COMMUNITY]` The camera **stitches in-camera** in this mode — real equirectangular
  output with zero desktop work.
- `[COMMUNITY]` Notable inversion: **the C200 has OSC from launch; the R210 did not.** On
  this axis the 2016 model is the more capable one.
- `[VERIFIED, by me]` `OSC` appears ×164 in the C200 firmware image.

### Evidence AGAINST
- `[INFERRED]` `camera.getLivePreview` (MJPEG) is documented by Google as **API level 2+**.
  A level-1 camera probably lacks it.
- `[COMMUNITY]` In-camera stitching takes 10–15 s per photo and is reportedly cropped — so
  even at best this is stills, not video.

### The gap
**`[UNKNOWN]` Nobody has ever dumped `/osc/info` from a C200.** The "C200 is level 1"
claim rests on app-level statements, not device-level probing. This is the single cheapest
unresolved question in the entire project.

### Effort
**10 minutes.** Two curl commands.

### Fastest falsification
```bash
curl -s http://192.168.107.1/osc/info | python3 -m json.tool
```
Read `apiLevel` and the command list. If `camera.getLivePreview` is absent, Path 2 is
dead for **video** — but still valuable for stills.

---

# Path 3 — Near-live segment pull (guaranteed-ish fallback)

**Hypothesis:** record in loop mode and pull completed files off the camera's HTTP file
server as they close.

### Evidence FOR
- `[VERIFIED]` The camera runs a plain HTTP file server on **port 9001** rooted at DCIM.
  Confirmed open in an idle nmap — no RVF trigger needed.
- `[VERIFIED]` Video-looping mode with a 5-minute cycle flushes a file **every 1 minute**.
- Requires no reverse engineering at all.

### Evidence AGAINST
- `[VERIFIED]` **It is not live.** Latency floor ~60–90 s. Normal recordings split at
  1.8 GB (~8 min at 30 Mbit/s).
- Thermal limits still apply.

### Effort
**~1 hour.** A polling script.

### Verdict
Not a webcam. But it is the **only path with a near-certain outcome**, and worth building
as a known-good baseline while Path 1 is uncertain.

---

# Path 4 — Screen-mirror the Android app (works TODAY, ugly)

**Hypothesis:** run the modded Gear 360 Manager on Android, mirror to the Mac, capture.

### Evidence FOR
- `[COMMUNITY]` **This is the only approach anyone has actually got working.** From a
  C200 owner: *"best I managed was using the modded Gear360 Manager and running scrcpy on
  my mac, then OBS to capture the screencast."*
- `[COMMUNITY]` Live View is confirmed working on the C200 with the modded app — the
  constraint is phone horsepower, not camera model.
- `[COMMUNITY]` A variant with an Android SBC and HDMI out reportedly worked well:
  *"Трансляция в реальном времени работает"* (real-time transmission works) — though
  `[UNKNOWN]` whether that user's camera was a C200 or R210; he never says.

### Evidence AGAINST
- Quality is whatever survives a screen recording; you inherit the app's letterboxing and
  UI.
- Requires an Android phone permanently in the loop.
- `[COMMUNITY]` The same C200 owner's conclusion: *"I don't think a mod is going to appear
  that will give us the full USB webcam functionality."*

### Effort
**~1 hour**, mostly installing things.

### Verdict
**Build this early as your reference.** Even if you never ship it, it proves your camera's
live view works *at all* — which is a prerequisite for diagnosing Path 1, and it settles
the AQK1 viewfinder question on your specific hardware.

---

# Path 5 — Start RVF from a camera-side root shell

**Hypothesis:** with root, invoke whatever `di-camera-app` invokes.

### Evidence FOR
- `[COMMUNITY]` Root shell is achievable.
- `[VERIFIED, by me]` `RVF` ×285, `dfmsd` ×23, `dfmstool` ×14 in the C200 firmware — the
  machinery is there.

### Evidence AGAINST
- `[COMMUNITY]` **No CLI verb has ever been found.** *"everything is managed by a single
  executable di-app… I was not able to find a way to programmatically interact with the
  camera."*
- `[COMMUNITY]` **`st app nx capture single` REBOOTS the C200.** Poking `st` here is
  actively dangerous.
- `[VERIFIED]` The persistent mod hijacks `wlan0` onto your home WLAN, which
  `[INFERRED]` **conflicts** with the Wi-Fi Direct / SoftAP paths RVF needs. You may be
  unable to have shell and RVF simultaneously.

### Effort
**Days, unbounded.** Binary reverse engineering of a monolithic proprietary app.

### Verdict
**Do not start here.** It is only worth attempting if Path 1 proves the network trigger is
impossible. And note it is not needed for Path 1 at all.

---

# Path 6 — `/dev/mem` framebuffer scrape (NX technique)

### Evidence AGAINST — this is close to disqualifying
- `[VERIFIED]` `nx-remote-controller-mod` hard-aborts: `die("unsupported nx model.")` on
  anything outside {NX1, NX300, NX300M, NX2000, NX3000, NX500}.
- `[VERIFIED]` Its framebuffer addresses are per-model hardcoded tables with **no Gear 360
  entry**.
- `[INFERRED]` **The C200 has no live-view LCD** — only a small status display. The buffer
  this technique scrapes may not exist.
- `[UNKNOWN]` Even if physical camera-frame addresses were found, they visibly **changed
  within a single session** in the device log, so any implementation needs runtime
  discovery, not constants.

### Effort
**Weeks, high risk, may be impossible.**

### Verdict
**Do not attempt.** Listed only so it is explicitly ruled out.

---

# Path 7 — USB webcam (UVC)

### Verdict: **not achievable.** `[COMMUNITY]`

- No USB video path exists on the camera.
- `[VERIFIED]` The firmware **refuses to charge while streaming**, so even a hypothetical
  USB video mode could not run indefinitely.
- Every "Gear 360 as webcam" guide on the internet is **R210-only** and works by
  capturing ActionDirector's *Live Broadcast* window — a feature the C200 does not have.

---

# Ranking summary

| # | Path | Probability | Effort | Risk | Do it? |
|---|---|---|---|---|---|
| 2 | OSC `/osc/info` probe | — | 10 min | none | **First. Cheapest question in the project.** |
| 1a | RVF with phone in loop | High | 2–5 h | none | **Yes — decomposes the problem** |
| 4 | Screen-mirror reference rig | High | 1 h | none | **Yes — build as baseline** |
| 1b/1c | RVF phone-free | Medium | 2–5 h | none | **Yes — the real prize** |
| 3 | Segment pull | Very high | 1 h | none | Yes — guaranteed fallback |
| 5 | Camera-side RVF trigger | Low | days | **high** | Only if 1 fails |
| 6 | `/dev/mem` scrape | Very low | weeks | **high** | No |
| 7 | USB webcam | ~zero | — | — | No |

**Note that the top five paths are all zero-risk to the hardware.** None of them requires
rooting the camera, and none requires writing to the root filesystem. That is the single
most important scheduling fact in this project: **the live-video question can be almost
fully explored on a bone-stock camera.**

---

# Cross-cutting unknowns that affect every path

- `[UNKNOWN]` **Can RVF be entered without Bluetooth/the phone?** The crux.
- `[UNKNOWN]` **Does AQK1 break the viewfinder?** Directly contradictory community
  reports. All wire-level evidence in this dossier comes from **APE4**, the *oldest*
  build. **Do not flash a working unit to AQK1 while chasing live video.**
- `[UNKNOWN]` **Real throughput.** 22 Mbit/s over the camera's Wi-Fi is unlikely to
  sustain; the middle/low variants are probably the usable ones. Never measured.
- `[UNKNOWN]` **Is the stream dual-fisheye?** `[INFERRED]` yes from 2560×1280 2:1 and the
  `lensInfo/horiAngle/vertiAngle` fields — but nobody has looked at a decoded frame.
- `[UNKNOWN]` **The `livestream_low` filename.** The camera log truncates at `http://192`.
  `livestream_low.avi` is a **guess**. High and middle are confirmed.
- `[UNKNOWN]` **The 5-byte chunk question.** Java impl keeps, Kotlin impl strips.
  `[INFERRED]` keep. One `ffprobe` settles it.
