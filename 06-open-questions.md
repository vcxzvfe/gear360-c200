# Open Questions — ranked by how much they block progress

Every item is genuinely unresolved. Nothing here is a guess dressed as a gap.
"Cost to answer" assumes the bench setup in `05-experiment-plan.md`.

---

# TIER 1 — Blocks the core goal

### Q1. Can the camera be driven into RVF mode without the Samsung Android app?
**Blocks:** the entire phone-free live-video goal.
**Status:** `[UNKNOWN]`. In every captured session the sequence is BT `liveview` → Wi-Fi on
→ SOAP `SetOperationState(changeToRVF)` → GET. It is unknown whether a laptop can skip
straight to the SOAP call, or even to the bare GET.
**Evidence that it might work:** `[VERIFIED]` Bluetooth's only job is switching the Wi-Fi
on — `[EXE_LIVEVIEW]` → `wifi_direct_activate() SUCCESS` in 3.66 ms, no stream started.
Everything after is ordinary HTTP/SOAP.
**Evidence against:** `[VERIFIED]` port 7679 is not listening when idle.
**Cost to answer:** ~30 minutes, **zero risk**. Experiments 7 and 8.
**This is the single most important unknown in the project.**

### Q2. Does the final firmware AQK1 break the viewfinder?
**Blocks:** whether you can safely standardise on the only firmware that the modern mods
require.
**Status:** `[COMMUNITY]` **directly contradictory reports.** One relayed account says
AQK1 kills both USB transfer and the phone live feed; three other C200 owners run AQK1
successfully, and both the 2026 telnet mod and the Gear VR remote shutter require it.
**Why it is dangerous:** `[VERIFIED]` **all** wire-level evidence in this dossier — ports,
TTTS, RVF, the 49 SOAP actions — comes from **`C200GLU0APE4`, the oldest of the six
builds.** Nothing guarantees it survives to AQK1.
**Cost to answer:** free if your two units differ (Experiment 1). Otherwise one flash —
which is a Tier-3 risk, so do not do it casually.
**Recommendation:** do not flash a working unit to AQK1 while chasing live video.

### Q3. Is the port-7679 stream reachable in SoftAP mode from a Mac?
**Blocks:** the practical Mac route.
**Status:** `[UNKNOWN]`. All primary log evidence is **Wi-Fi Direct** (`192.168.49.10`).
The SoftAP address `192.168.107.1` is `[VERIFIED]` from two independent sources, but
**`192.168.107.1` appears in no primary camera log.** `[INFERRED]` macOS cannot readily
join a Wi-Fi Direct P2P group, so SoftAP is the only practical path.
**Cost to answer:** ~15 minutes, zero risk. Experiment 4.

### Q4. Keep or strip the first 5 bytes of each `00VD` chunk?
**Blocks:** the demuxer.
**Status:** `[UNKNOWN]` — the two reference implementations **disagree**. Java keeps all
bytes; Kotlin reports `size - 5`.
**Best current answer:** `[INFERRED]` **keep them.** The "keyframe marker" values 64 and
38 decode as HEVC NAL headers (`0x40` → type 32 VPS, `0x26` → type 19 IDR), implying each
chunk starts with the Annex-B start code `00 00 00 01`.
**Cost to answer:** one `ffprobe` on a 30-second capture. Experiment 6.

---

# TIER 2 — Shapes the approach

### Q5. Can a root shell and the RVF stack coexist?
**Status:** `[UNKNOWN]`, and `[INFERRED]` there is real tension. The published C200 mod
puts `wlan0` on your home WLAN with a static IP via `wpa_supplicant`; RVF uses the
camera's own Wi-Fi Direct (`p2p0`) or SoftAP. **They may be mutually exclusive.**
**Why it may not matter:** if Q1 resolves favourably you never need shell for live video.
**Cost to answer:** Experiment 11, after Phase 3.

### Q6. Is the stream dual-fisheye, and at what real throughput?
**Status:** `[UNKNOWN]` on both counts. `[INFERRED]` dual-fisheye side-by-side from the
2560×1280 2:1 geometry and the `lensInfo/horiAngle/vertiAngle` fields, but **nobody has
looked at a decoded frame.** `[UNKNOWN]` whether 22 Mbit/s sustains over the camera's
Wi-Fi — almost certainly not; the middle/low variants are probably the usable ones, and
**no measurement exists.**
**Cost to answer:** falls out of Experiment 6 for free.

### Q7. What is the `livestream_low` filename?
**Status:** `[UNKNOWN]`. The camera log truncates mid-URL at `http://192`.
`livestream_low.avi` is a **guess, not evidence.** High and middle are `[VERIFIED]`.
**Cost to answer:** the SOAP `GetInfomation` response returns all three (Experiment 8), or
read the SCPD off your own camera's SD card.

### Q8. Does the C200 expose OSC live preview?
**Status:** `[UNKNOWN]`. `[INFERRED]` probably not — `camera.getLivePreview` is documented
as API level 2+, and the C200 is described everywhere as level 1. **But nobody has ever
dumped `/osc/info` from a C200**, so "level 1" rests on app-level statements rather than
device-level probing.
**Cost to answer:** one `curl`, zero risk. Experiment 3. **Cheapest open question in the
project.**

### Q9. Is the RVF stack functional in factory/test mode?
**Status:** `[UNKNOWN]`. `dfmsd` overlays a test UI in factory mode. Whether the normal
camera app — and therefore RVF — still works there is undetermined, and it decides whether
shell-based experiments can be combined with streaming experiments at all.
**Cost to answer:** Experiment 11.

### Q10. What does the empty `dfms.tg` do?
**Status:** `[UNKNOWN]`. It appears in **no** NX documentation, and my byte search of the
C200 firmware found it zero times (though the image is compressed, so that proves nothing).
Hypothesis (untested): it suppresses the test-mode overlay.
**Cost to answer:** a clean A/B, Experiment 10. Nobody has run it.

---

# TIER 3 — Safety-relevant, currently unanswerable without risk

### Q11. Does `fw_upgrade_start` validate the firmware header's project name?
**Why it matters:** this decides whether "R210 firmware on a C200" is a *rejection that
leaves a half-written flash* or an *unchecked cross-model write*. It is the mechanism
behind the worst documented failure mode.
**Status:** `[UNKNOWN]`. `[VERIFIED, by me]` the information is certainly available to it —
the image header carries `SMC200` in plaintext at offset 0x0C, and `SMR210` appears zero
times in a C200 image.
**Cost to answer safely:** pull `/usr/sbin/fw_upgrade_start` off a working unit over telnet
and run `strings`/disassembly on it — **before** any flash. Do **not** answer it
experimentally.
**Practical stance regardless:** verify the header yourself (Experiment 0). Never rely on
the camera to catch your mistake.

### Q12. What separates a recoverable C200 from a terminal one?
**Status:** `[UNKNOWN]`. Both classes exist in the reports; nobody characterised the
boundary. Specifically: **does a dark C200 still power its SD reader at all?**
**Cost to answer:** cannot be answered without bricking a camera. Do not pursue.

### Q13. Does the C200 have a DOWNLOAD mode or a hardware UART?
**Status:** `[UNKNOWN]` for the C200. `[COMMUNITY]` A DOWNLOAD mode (OK+Menu+Power →
"Samsung SDB Interface") is reported **for the R210 only**, by a reporter who wrote
"YMMV". `[VERIFIED]` No UART/JTAG is annotated in the FCC internal photos, and the official
manual documents no hardware reset at all.
**Note:** `[VERIFIED]` the "USB serial console" in the 2026 mod is a **software USB gadget**
(`/dev/ttyGS0`), not a hardware UART — it only exists after Linux boots, so it is useless
for recovering a dead camera.
**Cost to answer:** the button combo is free to *try* on a working unit and is
`[INFERRED]` low-risk; finding a UART would require opening Unit B and high-resolution
board photography.

### Q14. What does `/usr/bin/system-recovery` do?
**Status:** `[UNKNOWN]`. It appears in a real C200 `/usr/bin` listing and **nobody in the
community has ever investigated it.** It could be a fourth recovery tier.
**Cost to answer:** free — `ls -l` and `strings` it during Experiment 9. **Cheap, and
potentially very valuable.**

### Q15. Why does the snapshot repair work for some and not others?
**Status:** `[UNKNOWN]`. `/usr/bin/erase_snapshot.sh` and `make_snapshot.sh` contents have
never been published; preconditions (free space, battery level, SD present) are unknown.
Public success rate ≈ 1 in 3.
**Cost to answer:** free — `cat` both scripts during Experiment 9, **before** you ever need
them. **Do this.**

---

# TIER 4 — Nice to know, blocks nothing

### Q16. The C200's real `capdtm` user-data table.
`[CORRECTED]` The table circulating as "C200" is the **R210's**, and at least one quoted
field (`TIMELAPSESIZE_UD_360`) exists in no source anywhere. `[VERIFIED, by me]` `capdtm`
does appear ×17 in the C200 firmware, so the namespace is real — but the C200's actual IDs
are `[UNKNOWN]`. Nobody has published `st cap capdtm usrlist` from a C200.
**Relevant to safety:** this is why the shipped mod scripts' `capdtm` lines must be
deleted (`03-safety-and-recovery.md` §1.4).

### Q17. Does the camera draw operating power from USB while not charging?
`[VERIFIED]` The manual says it cannot **charge** while streaming. `[UNKNOWN]` whether it
still draws bus power — if it does, USB might extend runtime without charging.
**Cost:** a USB power meter and 20 minutes. Nobody has measured it.

### Q18. Exact thermal thresholds and their units.
`[UNKNOWN]`. Log values `640/650`, `670/690`, `690/710`; 0.1 °C is the natural reading
(~65–71 °C) but this is `[INFERRED]` from context, not confirmed.
**Do not attempt to raise these.** Overriding a Li-ion over-temperature cutoff is a safety
question, not a software one.

### Q19. Which model did the Android-SBC live-view rig use?
`[COMMUNITY]` A 4PDA user drove live view from an Asus Tinker Board with HDMI out and
reported it worked well. He never states C200 vs R210. If C200, it is a ready-made
live-video-to-a-capture-card answer.

### Q20. Does `/dev/video*` exist on the C200 at all?
`[UNKNOWN]` — **nobody has ever posted an `ls /dev` from a C200.** `[INFERRED]` probably
not: the image path is proprietary DRIMe5 char devices (`/dev/d5_mipi`), and the expert NX
tooling never uses V4L2 either.
**Cost:** free — the Experiment 9 recon script already answers it.

---

# Questions this dossier CLOSED

Recorded so they are not reopened.

| Question | Resolution |
|---|---|
| Does the `.adj` filename matter on the C200? | **No.** `[VERIFIED]` Samsung's own factory text inside the C200 firmware: *"info.tg : Name of file to execute (paf_adj_restore.adj)."* The name is arbitrary; `info.tg` names it. |
| Must the payload script be named `test.sh`? | **No.** `[VERIFIED]` Folklore. Two working C200 packages use `upgrader.sh` and `mods.sh`. |
| Can the C200 livestream? | **Yes, locally.** `[VERIFIED]` The widely-quoted "requires a 2017 Gear 360" refers to Samsung **Live Broadcast** (RTMP to YouTube), not the local viewfinder. |
| Will `ffplay` open the stream? | **No.** `[VERIFIED]` It is TTTS/HEVC, not AVI. The `.avi` name, the `video/x-avi` MIME and the `AVC_MP4_...` DLNA profile are all mislabels. |
| Does `keyscan360` button triggering work on C200? | **No.** `[VERIFIED]` NX/R210 code; tested on a C200 and it failed; the author removed it. |
| Is the published C200 `capdtm` table real? | **No.** `[VERIFIED]` It is the R210's, with at least one fabricated field. |
| Are `/usr/mod/*.sh` persistence hooks? | **No.** `[VERIFIED]` They appear only as the *symptom* of filesystem corruption. |
| Does the ACL block SOAP? | **Unsupported.** `[VERIFIED]` All observed rejections were on device-*description* requests; SOAP POSTs showed no check. |
| Is the firmware image obtainable? | **You already have it, hash-verified.** `[VERIFIED]` SHA256 `150bc48…c48db`, 279,094,189 bytes, header project `SMC200`. |
