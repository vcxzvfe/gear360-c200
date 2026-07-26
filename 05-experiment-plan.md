# Bench Experiment Plan — SM-C200

**Ordering principle: every non-destructive observation happens before any write to the
device. Phases 0–2 do not modify the camera in any way — no SD card files, no root, no
firmware. The camera stays bone stock through Experiment 8.**

This ordering is not caution theatre. The live-video stream is served by **stock
firmware**, so the highest-value question in the project can be answered without ever
putting the hardware at risk.

Standing rules:
- **Unit A** = the guinea pig. **Unit B** = sealed, known-good reference. Do not modify B.
- Record firmware version of both units before anything (Experiment 1).
- `[UNKNOWN]` markers below are real gaps. If an experiment's expected output is marked
  unknown, you are generating new knowledge — write down what you actually see.

---

# PHASE 0 — Desk work, no hardware

## Experiment 0 — Verify the recovery image
**Goal:** confirm you hold a genuine, uncorrupted C200 firmware before anything else.
**Risk:** none.

```bash
shasum -a 256 C200GLU0AQK1_171121_1257_REV00_user.bin
stat -f %z    C200GLU0AQK1_171121_1257_REV00_user.bin
xxd -l 48     C200GLU0AQK1_171121_1257_REV00_user.bin
```

**Expected** `[VERIFIED]`:
```
150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db
279094189
00000000: 534c 5000 302e 3835 0000 0000 534d 4332  SLP.0.85....SMC2
00000010: 3030 0000 0000 0000 0000 0000 534d 4332  00..........SMC2
00000020: 3030 474c 5530 4151 4b31 0000 0a00 0000  00GLU0AQK1......
```

**Failure signature:** hash mismatch, or the string `SMR210` anywhere.
**ABORT CONDITION:** if the hash does not match — **stop the entire project.** You have no
recovery image. Every Samsung host is dead; obtain and verify a good copy first.

**Then:** copy to two offline locations.

---

# PHASE 1 — Pure observation (camera unmodified)

## Experiment 1 — Inventory both units
**Goal:** know your starting state, and settle the AQK1 question for *your* hardware.
**Risk:** none.

> **CORRECTION `[VERIFIED — official SM-C200 manual]`.** An earlier draft of this plan said
> to "read the firmware version from the camera menu". **There is no such menu item on the
> camera body.** The manual exposes the firmware version only through the phone app
> (*Samsung Gear 360 → MORE → Settings → Gear 360 firmware version*), and the camera's own
> Menu key offers only: short press → `Video / Photo / Time lapse / Video looping /
> Settings`; press-and-hold → `Gear 360 Manager / Remote control / Google Street View`.
>
> **Therefore, if you have no Android phone, do Experiment 3 first** — OSC `/osc/info`
> returns `firmwareVersion` and `model`, so it answers this experiment without a phone,
> without an SD card, and without changing any camera setting. Experiment 3 is then both
> the cheapest experiment in the project *and* the only phone-free way to inventory a unit.

On each camera record: unit label, firmware string, whether the app connects, whether live
view works. Obtain the firmware string by **either** the phone app path above **or**
Experiment 3's `/osc/info` (no phone required).

**Expected:** one of `C200GLU0APC9 / APE4 / API1 / AQC1 / AQF1 / AQK1` `[COMMUNITY]`.
`[UNKNOWN]` whether OSC's `firmwareVersion` field reports that same build-ID format or a
shorter marketing version string — record verbatim whatever it returns.

**Why this matters:** `[COMMUNITY]` there are **directly contradictory** reports about
whether the final build `AQK1` breaks the viewfinder. All wire-level evidence in this
dossier comes from **APE4**, the *oldest* build. If your units differ, **that is a gift** —
you have a natural A/B.

**ABORT CONDITION:** none. Pure observation.
**DO NOT** flash either unit to AQK1 at this stage, however tempting.

---

## Experiment 2 — Reference rig: prove live view works at all
**Goal:** establish that *your* camera can produce live video, before debugging why a Mac
can't get it.
**Risk:** none to the camera.

Install the modded Gear 360 Manager on an Android phone `[COMMUNITY]`, pair with Unit A,
open live view.

**Expected:** live 360 preview on the phone.
**Failure signature:** app connects but "Camera"/viewfinder mode does nothing.
**If it fails:** you may be on a firmware with the reported viewfinder breakage
`[COMMUNITY]`. Try Unit B. Note the firmware difference — this is a real finding.

**ABORT CONDITION:** none.
**Value:** this is also Path 4 (screen-mirror + scrcpy + OBS) — the only approach anyone
has ever got working. Even as a fallback it is worth having.

---

## Experiment 3 — OSC probe ★ CHEAPEST QUESTION IN THE PROJECT
**Goal:** settle whether the C200 exposes an OSC live preview. **Nobody has ever done
this.**
**Risk:** none.

> **PREREQUISITE — a memory card must be inserted, or the menu item is not there.**
> `[VERIFIED on hardware, 2026-07-27]` A C200 with no card in it shows only
> `Gear 360 Manager / Remote control` in the press-and-hold menu — **`Google Street View`
> is absent.** This is not a firmware or region difference: the launch manual
> (English, 05/2016, Rev.1.0) documents all three items.
>
> `[VERIFIED — manual]` The C200 has **no internal storage at all**: *"A memory card must
> be inserted to take photos or record videos."* `[COMMUNITY]` Samsung's own support
> material shows other storage-dependent items (e.g. card formatting) vanishing from the
> menus under the same condition. `[INFERRED]` Street View mode is hidden by the same
> gate, since the mode exists to capture photos.
>
> **Diagnostic:** the camera's status display reads `No card` when none is inserted.
>
> Insert an **ordinary blank card, FAT32, with no mod files on it whatsoever.** At this
> stage the card is plain storage — no `info.tg`, no `.adj`, nothing. Zero risk.

Put Unit A into **Google Street View mode** on the camera body. The exact key sequence,
`[VERIFIED — official SM-C200 manual]`, is **two** steps and the first one is easy to miss:

> 1. **Press and hold** the Menu key.
> 2. Press the Menu key until `Google Street View` appears, then press the OK key.

Short-pressing alone will never reach it: the short-press menu is only
`Video / Photo / Time lapse / Video looping / Settings`. The press-and-hold menu is
`Gear 360 Manager / Remote control / Google Street View`.

`[COMMUNITY]` The camera then creates its own AP whose SSID ends in `.OSC`, with an
**8-digit password shown on the camera LCD**. Join it from the Mac.

```bash
ipconfig getifaddr en0                 # your address on the camera's subnet
netstat -rn | grep -m1 default         # the camera IS the gateway — use THIS address below
curl -s -m 10 http://192.168.107.1/osc/info | python3 -m json.tool
```

`[COMMUNITY]` `192.168.107.1` is what baardove observed on a 2016 Gear 360, and his own
README warns *"Different firmware and different cameras might use different range and
address."* **Use the gateway your Mac was actually assigned**, not the literal address above.

**Expected** `[INFERRED — OSC spec; not C200-verified]`: JSON containing `manufacturer`,
`model`, `serialNumber`, `firmwareVersion`, `apiLevel`, and an `api` array.

**What to look for:**
- `firmwareVersion` — this is also the phone-free answer to Experiment 1.
- `apiLevel` — is it `[1]` or does it include `2`?
- Is `camera.getLivePreview` present in the `api` list?

**Calibrate your expectations before running this.** `[COMMUNITY]` baardove's client
describes the 2016 Gear 360 as **"Open Spherical Camera API level 1"**, and
`camera.getLivePreview` is an OSC **level 2** command. So the most likely outcome is
**absent** — this experiment probably *closes* a path rather than opening one. Run it
anyway: it is 10 minutes, it is the only phone-free way to read the firmware version, and
no C200 `/osc/info` dump has ever been published.

**Failure signature:** connection refused / timeout. Then try the gateway address your Mac
was actually assigned (`netstat -rn | grep default`) — `[COMMUNITY]` the address range may
vary by firmware.

**ABORT CONDITION:** none.
**Outcome value:** if `camera.getLivePreview` is present, that is a **major** result — a
standards-based MJPEG live preview with no reverse engineering at all. If absent, Path 2
is closed for video and you have still produced the first published `/osc/info` dump from
a C200.

---

## Experiment 4 — Port scan the camera in every mode
**Goal:** find out which services listen, when.
**Risk:** none.

With the Mac joined to the camera's AP, in **each** camera mode you can reach (Street
View/OSC, Wi-Fi mode, idle, and — via Experiment 2 — during live view):

```bash
nmap -Pn -p 1-10000 192.168.107.1
```

**Expected** `[VERIFIED, but measured over Wi-Fi Direct not SoftAP]`: idle shows
`53, 7676, 9001` open. `[INFERRED]` **7679 binds only while RVF is active.**

**The result that matters:** is **7679** open in any mode *without* the phone app running?
If yes, the entire Bluetooth dependency collapses.

**Failure signature:** all ports filtered → you are probably not actually on the camera's
network. Verify with `ping 192.168.107.1`.

> **macOS limitation `[INFERRED]`:** macOS cannot readily join a **Wi-Fi Direct / P2P**
> group. The device log captures Wi-Fi Direct mode (`192.168.49.10`), but the practical
> Mac route is the camera's **SoftAP** (`192.168.107.1`). Expect to work in SoftAP.

**ABORT CONDITION:** none.

---

## Experiment 5 — Capture the stream, phone in the loop
**Goal:** decouple *transport* from *trigger*. Prove you can receive bytes while the phone
does the triggering.
**Risk:** none.

1. Start live view via the Android app (Experiment 2).
2. Determine the camera's address on that network from the Mac.
3. While live view is running:

```bash
curl -v --http1.1 -A 'Android Linux' \
     --max-time 30 \
     http://<CAMERA_IP>:7679/livestream_high.avi -o /tmp/high.ttts
ls -l /tmp/high.ttts
```

**Expected** `[VERIFIED — this exact request/response is in the camera's own log]`:
```
< HTTP/1.1 206 Partial Content
< Content-Type: video/x-avi
```
and a growing file.

**Failure signature:**
- Connection refused → 7679 not bound; the camera is not in RVF.
- 503 → the User-Agent ACL bit you. Retry with `-A 'SEC_RVF_ML_02:00:00:00:00:00'`
  `[VERIFIED — that exact UA was accepted by a real C200]`.
- Zero bytes → the app may hold an exclusive session. Try stopping live view on the phone
  the instant you fire curl.

**ABORT CONDITION:** none.
**This is the single highest-value experiment in Phase 1.** It converts the project from
"unknown" to "decode problem".

---

## Experiment 6 — Identify the captured bytes
**Goal:** confirm the container and settle the 5-byte disagreement.
**Risk:** none (desk work).

```bash
xxd -l 256 /tmp/high.ttts
```

**Expected** `[VERIFIED]`: the file begins with ASCII **`TTTS`** (`54 54 54 53`), followed
by `VID0` / `AUD0` / `VRO0`, then `LIST` / `movi`, then repeating `00VD` / `00AU` / `00VR`
chunk tags.

**It will NOT be a RIFF/AVI file** — the `.avi` name and `video/x-avi` MIME are mislabels
`[VERIFIED]`.

Then extract the `00VD` payloads and test the NAL hypothesis:

```bash
# after demuxing 00VD payloads into raw.hevc:
ffprobe -f hevc raw.hevc
```

**Expected** `[INFERRED]`: `hevc` stream, 2560×1280, ~29.97 fps.

**The open question this settles** `[UNKNOWN]`: whether to keep or strip the first 5 bytes
of each video chunk. `[INFERRED]` from NAL analysis: **keep them** (`0x40` = VPS,
`0x26` = IDR, preceded by the Annex-B start code). If `ffprobe` rejects the stream, try
stripping 5 and compare.

**Also record** (nobody has ever published these):
- Actual sustained bitrate.
- Whether frames are **dual-fisheye side-by-side** `[UNKNOWN]` or something else.
- Whether `00VR` gyro data is present and sane.

**ABORT CONDITION:** none.

---

# PHASE 2 — Phone-free attempts (camera still unmodified)

## Experiment 7 — Bare GET with no phone at all
**Goal:** test whether the HTTP GET alone triggers RVF.
**Risk:** none.

No Bluetooth pairing, no app. Put the camera into its own AP mode, join from the Mac:

```bash
curl -v --http1.1 -A 'Android Linux' --max-time 20 \
     http://192.168.107.1:7679/livestream_high.avi -o /tmp/nophone.ttts
```

**Expected:** `[UNKNOWN] — this is the crux experiment of the whole project.`
- If it returns 206 and bytes → **the Bluetooth dependency is dead** and Path 1b works.
- If connection refused → 7679 is not bound without a prior RVF trigger. Go to
  Experiment 8.

**Failure signature:** `Connection refused` is the *informative* failure, not an error.
**ABORT CONDITION:** none.

---

## Experiment 8 — SOAP trigger
**Goal:** put the camera into RVF over the network.
**Risk:** none to hardware.

First read the device description:

```bash
curl -s -A 'SEC_RVF_ML_02:00:00:00:00:00' http://192.168.107.1:7676/smp_2_
```

**Expected** `[VERIFIED]`: UPnP XML naming a ContentDirectory service with
`controlURL /smp_4_`.

Then the mode change `[VERIFIED — this is exactly what the app sends]`:

```
POST /smp_4_ HTTP/1.0
Content-Type: text/xml; charset="utf-8"
HOST: 192.168.107.1
SOAPACTION: "urn:schemas-upnp-org:service:ContentDirectory:1#SetOperationState"
Connection: close
```

with `StateEvent = changeToRVF`, then a second call with
`SOAPACTION: "…ContentDirectory:1#GetInfomation"` which returns `StreamUrl`.

> `[UNKNOWN]` **The exact SOAP body XML has never been published.** The camera log records
> the *headers* and `Content-Length: 364`, but not the envelope contents. You will need to
> construct a standard UPnP SOAP envelope for the `SetOperationState` action using the
> argument names from the camera's own `ContentDirectory_1.xml`. **Do not guess the body
> from this document — read the SCPD.** It is available in the gear360reveng repo at
> `logfiles/dot.config/RVF/xml/ContentDirectory_1.xml`, and the camera writes its own copy
> to `/mnt/mmc/.config/RVF/xml/` on your SD card — **so you can read it off your own
> camera's card**, which is the authoritative version for your firmware.

**Failure signature:** 503 ServiceUnavailable → the User-Agent ACL. `[VERIFIED]` the
accepted pattern is `SEC_RVF_ML_<mac>`.

**ABORT CONDITION:** none. If both 7 and 8 fail, Path 1 falls back to 1a (phone in loop),
which Experiment 5 already validated.

---

# PHASE 3 — SD card, factory mode (reversible; first modification)

**Do not enter Phase 3 until Phases 1–2 are exhausted.** Nothing here is needed for live
video if Experiment 5 or 7 succeeded.

## Experiment 9 — Read-only shell proof
**Goal:** prove the `info.tg` chain fires on *your* unit, writing nothing to the camera.
**Risk:** low. Reversible by deleting one file.

Prepare the card per `02-c200-shell-procedure.md` §A.2 with the read-only `recon.sh`.

**Expected:** camera boots into the factory/test UI (green dots / test menu) and
`recon.txt` appears on the card containing `uid=0(root)`.

**Failure signature:** no `recon.txt` → the chain did not fire. Check byte-exactness of
`info.tg` and the `.adj` (**trailing space**), and that the `.adj` names your script.

**ABORT CONDITION:** if the camera does **not** boot normally after you remove `info.tg`,
stop and go to `03-safety-and-recovery.md` Tier 0.

**Reversal:** delete `info.tg`. `[VERIFIED]` Nothing on the camera was changed.

**New knowledge you will produce here:** the inherited `PATH` on your firmware, and
whether `/dev/video*` exists — **nobody has ever posted an `ls /dev` from a C200.**

---

## Experiment 10 — The `dfms.tg` A/B
**Goal:** determine what the mysterious empty `dfms.tg` file does.
**Risk:** same as Experiment 9.

Run Experiment 9 twice, identically, except:
- Run A: `info.tg` = `"nx_cs.adj\n\n"`, no `dfms.tg`.
- Run B: `info.tg` = `"nx_ft.adj\ndfms.tg\n"`, plus an empty `dfms.tg`, `.adj` renamed
  accordingly.

**Observe:** does the test-mode overlay / green-dot UI appear in one and not the other?
Does the script execute in both?

**Expected:** `[UNKNOWN]`. Hypothesis (untested): `dfms.tg` suppresses the `dfmsd` test
overlay. **This is an open question nobody has answered** — a clean result here is
publishable.

**ABORT CONDITION:** same as Experiment 9.

---

## Experiment 11 — Telnet, and the Wi-Fi conflict
**Goal:** get a root shell, and find out whether shell and RVF can coexist.
**Risk:** low, still SD-only.

Use the **minimal** telnet script from `02-c200-shell-procedure.md` §A.3.

> **Do NOT run the shipped `mods.sh` / `G360POWE_G360POW.sh` unmodified.** `[VERIFIED]`
> They hijack `wlan0` onto your home WLAN **and** contain `st cap capdtm setusr` lines
> copy-pasted from the R210/NX documentation. Delete the `capdtm` lines. See
> `03-safety-and-recovery.md` §1.4.

**The question to answer** `[UNKNOWN]`: with the camera in factory mode and telnet up, is
the RVF stack still functional? Re-run Experiment 5 or 7 while telnet is live.

**Expected:** `[UNKNOWN]`. `[INFERRED]` there is a real risk they are mutually exclusive:
shell wants `wlan0` on your LAN, RVF wants the camera's own AP / Wi-Fi Direct.

**ABORT CONDITION:** if telnet requires reconfiguring Wi-Fi and that kills RVF, **stop and
reconsider** — you may not need shell at all, since Phase 1/2 can deliver video without it.

---

# PHASE 4 — Persistence (only if genuinely required)

**Do not enter Phase 4 to satisfy curiosity.** `[COMMUNITY]` Public success rate for the
snapshot repair is roughly **1 in 3**, and two C200 owners were never recovered.

Preconditions, all mandatory:
1. Phases 1–3 complete and documented.
2. A concrete reason persistence is required that Phase 1–3 cannot satisfy.
3. Verified firmware image on hand (Experiment 0) **and** a prepared rescue SD card.
4. Unit B still untouched.

Then follow `02-c200-shell-procedure.md` Part B, which is kjuanman's 12-step sequence.
**`mount -o remount,rw /` is the first irreversible action in this project.**

---

# Decision tree

```
E0 hash fails ─────────────────────────► STOP. Get a valid image first.
E3 shows getLivePreview ───────────────► Take the OSC path. Easiest win available.
E5 returns 206 + bytes ────────────────► Transport solved. Write the TTTS demuxer.
E7 returns 206 with NO phone ──────────► BEST CASE. Phone-free live video. Publish it.
E7 refused, E8 works ──────────────────► Phone-free via SOAP. Also excellent.
E7 and E8 both fail ───────────────────► Fall back to phone-in-loop (E5) or Path 4.
E5, E7, E8 all fail ───────────────────► Live video may need Path 5 (hard) — reassess
                                          scope before risking hardware.
```

**Note that the entire decision tree above resolves without modifying the camera once.**
Phases 3 and 4 are optional extensions, not prerequisites.
