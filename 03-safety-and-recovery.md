# Safety and Recovery — SM-C200

**Read this completely before powering on a camera with a modified SD card.**

The SM-C200 has **no hardware recovery mode, no documented JTAG or UART, and no button
combination that reaches a bootloader.** Every documented recovery path requires the
camera to still boot Linux far enough to mount the SD card and run `dfmsd`. If it stops
booting, there is currently **no published way back.**

---

# 1. What NOT to do

## 1.1 NEVER put SM-R210 firmware — or any R210 file — on a C200

`[COMMUNITY, strongest evidence in the entire corpus]` This is the documented hard-brick
path. It has killed multiple cameras and **has no known recovery.**

- kras891 flashed `R210GLU0ARB2` onto a C200 → *"You flashed a 2017 model firmware on a
  2016 model device. You've bricked it, sorry. No known solution to that."*
- Drag0nR13: *"I mistakenly flashed the SM-R210 firmware onto my SM-C200 Gear 360 … no
  LEDs, no signs of power, and no USB detection."* → *"As far as is known, there is no
  solution. It's bricked, sorry."*
- 4PDA, warning edited in **after** bricking reports: *"Способ ТОЛЬКО ДЛЯ камеры SM-R210 …
  Если применить к 2016го года камере (Круглые С200) у вас будет 100% кирпич."*

**Most R210 material on the internet is not labelled as R210.** The largest single risk in
this project is picking up a procedure, a script, or a `.bin` that was written for the
2017 camera. Verify the model attribution of *everything*.

## 1.2 NEVER interrupt a firmware flash

`[COMMUNITY]` Power loss, battery removal, or card removal mid-flash leaves the camera
cycling a blinking LED with no fix. One C200 owner used the *correct* C200 firmware and
the *correct* method, hit an error, and was never recovered — no reply was ever posted to
his request for help.

## 1.3 NEVER write to `/` until Part A is exhausted

`[COMMUNITY]` `mount -o remount,rw /` is the first irreversible action in this project.
Every documented C200 rootfs brick is downstream of it. See §5.

## 1.4 NEVER run the shipped mod scripts unmodified

`[VERIFIED — found during this dossier's verification, not previously reported]`
`G360POWE_G360POW.sh` in the C200 mod packages contains a block of `st cap capdtm setusr`
commands **copy-pasted from NX/R210 documentation.** The giveaway is in its own comments:

```
# set mode 0-movie, 1-smartauto, 2-program, 3-aperture, 4-shutter, 5-manual, 6-imode, ...
st cap capdtm setusr 0 4
st cap capdtm setusr 1 0x10004
st cap capdtm setusr 5 0x050001
st cap capdtm setusr 64 0x400000
```

A Gear 360 has no aperture priority, no shutter priority, no manual mode and no scene
modes — those are Samsung NX camera modes. I traced the identical text to
`ottokiksmaler/gear360_modding/README.md` (**"Repository for Samsung Gear 360 (2017)
modding"**) and to `nx500_nx1_modding/ST Commands.md`.

**These lines write factory user-data on your C200 using another camera's ID table.**
`[CORRECTED]` The circulating "C200 capdtm table" is in fact the R210's, and at least one
of its quoted fields (`TIMELAPSESIZE_UD_360`) exists in **no source anywhere.**

**Delete every `capdtm` line before running any of these scripts.**

## 1.5 NEVER assume an R210 technique transfers

Treat each of these as an **experiment**, never a step:

| Technique | Status |
|---|---|
| `keyscan360` double-click-Power trigger | **R210/NX only — tested on C200 and it did NOT work** `[VERIFIED]` |
| DOWNLOAD mode (OK+Menu+Power → Samsung SDB) | **R210 only — untested on C200** `[COMMUNITY]` |
| `/usr/sbin/bluetoothd` patch to escape factory mode | **NX only — CORRUPTS the C200** `[VERIFIED]` |
| `nx-remote-controller-mod` `/dev/mem` liveview | **NX only — hard-aborts on non-NX; no C200 addresses exist** `[VERIFIED]` |
| ActionDirector / OBS "webcam" recipes | **R210 only — C200 has no Live Broadcast** `[COMMUNITY]` |

## 1.6 NEVER lose the firmware image

`[VERIFIED]` Every original Samsung host is dead (NXDOMAIN). Wayback has no capture.
archive.org has no item. The only public mirror is behind an XDA login. **If you lose your
copy you may be unable to obtain another.**

---

# 2. Pre-flight checklist

Steps 1–8 are **fully reversible**. Step 9 onward are not.

### STEP 0 — BLOCKING. Verify the recovery image before touching hardware.

```bash
shasum -a 256 C200GLU0AQK1_171121_1257_REV00_user.bin
# expect: 150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db

stat -f %z C200GLU0AQK1_171121_1257_REV00_user.bin
# expect: 279094189
```

**Independently confirm it is a C200 image** — this is a 5-second check that would have
saved several bricked cameras:

```bash
xxd -l 48 C200GLU0AQK1_171121_1257_REV00_user.bin
```

`[VERIFIED, by me]` Expected output:

```
00000000: 534c 5000 302e 3835 0000 0000 534d 4332  SLP.0.85....SMC2
00000010: 3030 0000 0000 0000 0000 0000 534d 4332  00..........SMC2
00000020: 3030 474c 5530 4151 4b31 0000 0a00 0000  00GLU0AQK1......
```

magic `SLP\0` · version `0.85` · project **`SMC200`** · build **`SMC200GLU0AQK1`**

**If you see `SMR210` anywhere, STOP. That image will brick your camera.**

> `[UNKNOWN]` Whether `/usr/sbin/fw_upgrade_start` itself validates this header. It may
> not. **Do not rely on the camera to catch your mistake — the header check is *your* job.**

**Store two offline copies.** If the hash does not match, you have no recovery image and
must not proceed.

### Steps 1–8 — reversible

1. **Work on ONE camera.** Keep the second sealed as a known-good reference and donor.
2. **Charge to 100%.** `[COMMUNITY]` It is unknown whether the updater checks battery
   level. 4PDA guidance is ≥50% minimum; full is free insurance.
3. **Record the current firmware version** from the app or camera menu, for both units,
   before anything.
4. **Prepare the card.** Format **in the camera**, then add files from the Mac. Prepare a
   second identical rescue card and store it separately.
5. **Keep the camera on USB power** during any flash.
6. **Do the read-only dry run first** (Part A Stage 1). Prove the chain fires on *your*
   unit before you risk a write. Fully reversible — delete `info.tg`.
7. **Get telnet working** and confirm root login.
8. **Back up every file you intend to modify** (`cp x x.backup`) *before* editing.

### Steps 9–10 — IRREVERSIBLE

9. **`mount -o remount,rw /`** — from here you can corrupt the rootfs.
10. **`fw_upgrade_start`** — never interrupt, never remove battery or card, never lose power.

---

# 3. The correct shutdown procedure

This matters more than it looks, because of the hibernate design.

### To KEEP changes
Clean power off: **press and hold Power.** State is committed to the persistent snapshot on
a clean power-off.

### To DISCARD changes (the escape hatch)
**Pull the battery instead of powering off.**

`[COMMUNITY — NX-derived, `[INFERRED]` for C200]` On this platform, in-RAM state is only
committed on a clean power-off; pulling the battery abandons it. The NX documentation is
explicit:

> *"If you want to play around but **not save permanently** anything — don't power the
> camera off — pop the battery out."*

**This is NX-sourced.** It is `[INFERRED]` for the C200 by platform identity, not
demonstrated. It is nevertheless the only "undo" available mid-session, and it costs
nothing to use.

### The tension you need to know about

`[VERIFIED]` Samsung's own SM-C200 manual says the opposite for normal use:

> *"Turn off the Samsung Gear 360 before removing the battery. If you do not, the Samsung
> Gear 360 may be damaged."*

**Resolution `[INFERRED]`:** treat battery-pull as an **emergency discard**, not a routine
shutdown. Samsung's warning is primarily about in-flight writes (SD card / filesystem)
being interrupted. So:

- **Never** pull the battery while recording, while flashing, or while a snapshot is
  rebuilding.
- **Do** pull the battery if you have just made a change you want to abandon and you have
  not yet cleanly powered off.

`[VERIFIED]` The battery **is** user-removable: *"Press and slide the battery latch to
release the battery."* Part `EB-BC200ABE`. `[COMMUNITY]` 1350 mAh — **not** stated in the
manual text I extracted; this figure comes from replacement-battery listings.

### To exit factory/test mode
`[VERIFIED]` Power off, remove the SD card (or just delete `info.tg` from it), power on.
Nothing on the camera was changed.

---

# 4. Recovery runbook — ordered, escalating

Try in this exact order. Each tier assumes the previous failed.

### TIER 0 — Undo the trigger *(non-destructive)*
Power off → remove SD card → remove and reinsert battery → power on.
`[VERIFIED]` Removing `info.tg` alone exits factory/test mode.

### TIER 1 — Battery pull to discard uncommitted state *(non-destructive)*
If you have **not yet cleanly powered off** since your change, pull the battery rather
than powering off. `[INFERRED]` Unsaved in-RAM state is discarded instead of committed.

### TIER 2 — Snapshot rebuild *(for `Input/output error` symptoms; camera still boots)*

```
# regain telnet in factory mode, then:
sync; sync; sync
mount -o remount,ro /
/usr/bin/erase_snapshot.sh
# wait for reboot, telnet back in:
/usr/bin/make_snapshot.sh
# WAIT 3-5 MINUTES. Do not power off. Do not press any button.
poweroff
```

**`[CORRECTED]` This is not a reliable recovery.** Public record: teccheck — worked;
kjuanman — *"not worked for me"* on first attempt; rroseirac and pensadorxx — never
recovered. **Roughly 1 in 3.**

### TIER 3 — Full SD firmware reflash *(requires the camera to still boot Linux)*

Card root, FAT32, using the **verified** LalaTheDog file set:

```
C200GLU0AQK1_171121_1257_REV00_user.bin
info.tg      (11 bytes, "nx_cs.adj\n\n")
nx_cs.adj    (35 bytes, "shell script /mnt/mmc/upgrader.sh \n")
upgrader.sh
```

`[VERIFIED]` Power on; the flash starts **automatically** — there is **no** double-click
step on the C200. A progress bar appears, then `UPDATED`. Takes ~2 minutes. Then power off
and **delete all four files from the card.**

This restores rootfs, `/opt` **and** the swap/snapshot partition `[VERIFIED]` — which is
why it repairs snapshot inconsistency that Tier 2 cannot.

`[COMMUNITY]` The one documented C200 un-brick used a variation: a camera showing `Error`
on power-on was revived by flashing the **oldest** firmware (`APE4`) first, **then** the
newest (`AQK1`). If a straight AQK1 flash fails, try APE4 first.

### TIER 4 — None

If the camera does not power on, does not respond to USB, and does not run the SD script:
**there is no published recovery.** No download mode, no button combo, no documented
JTAG/UART, no service tool. **Treat that state as terminal.**

---

# 5. The one-way doors

Name them out loud before touching hardware.

1. **Flashing R210 firmware onto a C200.** Community-reported as a 100% brick, no recovery.
2. **Anything that stops the camera booting Linux.** Every recovery mechanism — factory
   mode, telnet, `erase_snapshot`, `fw_upgrade_start` — runs from **userspace**. Losing
   boot loses **all of them simultaneously.** This is the structural reason the C200 is
   unforgiving.
3. **An interrupted `fw_upgrade_start`.**
4. **Losing the firmware `.bin`.** Every host is dead. Download and hash-verify **before**
   you start; keep two copies.
5. **`mount -o remount,rw /`** — the moment rootfs corruption becomes possible.

---

# 6. Recoverable vs. terminal — how to tell

`[INFERRED]` from the pattern across all reports:

| Symptom | Class | Action |
|---|---|---|
| Test menu / green dots showing | Normal factory mode | Tier 0 |
| `Input/output error` on files you edited | Rootfs corruption, still boots | Tier 2 → Tier 3 |
| `Error` on power-on / progress bar / update loop | **Soft-bricked** | Tier 3 (APE4 then AQK1) |
| Boot loop, LCD shows something | **Soft-bricked**, probably | Tier 3 |
| Fully dark: no LED, no LCD, no USB enumeration | **Terminal** — no recovery ever reported | Stop |

`[UNKNOWN]` What exactly separates the recoverable from the terminal class. Both exist in
the reports; nobody characterised the boundary. Specifically: **does a dark C200 still
power its SD reader at all?** Unknown.

---

# 7. Thermal and power limits (not brick risks, but they will end your session)

`[VERIFIED]` Official SM-C200 manual, verbatim:

> *"You cannot charge the Samsung Gear 360 while recording a video, using the time lapse
> feature, or using the viewfinder remotely on the connected mobile device."*

**A permanently USB-powered streaming camera is impossible.** You are on the internal
battery whenever the stream is live.

> *"When recording videos or using the streaming feature for an extended period, the
> Samsung Gear 360 and its battery may heat up. If the temperature rises above a certain
> level, the Samsung Gear 360 will stop recording and turn off automatically."*

`[COMMUNITY]` Real-world continuous operation clusters around **40 minutes**, sometimes as
little as 10–20 at max resolution. `[COMMUNITY]` **Forced air cooling is dramatically
effective** — one user went from 7–10 minutes to over 40 with a small USB fan. This is the
standard mitigation.

`[VERIFIED]` Also: *"Large files will be divided into 1.8 GB units and saved."*

`[UNKNOWN]` Whether the camera still draws *operating* power from USB while not charging.
The manual only says it cannot charge. If it does draw bus power, USB might extend runtime
without charging. **Measurable with a USB power meter — nobody has done it.**

`[UNKNOWN]` The exact thermal thresholds. Values appear in the device log
(`warning/poweroff` pairs `640/650`, `670/690`, `690/710`) and 0.1 °C is the natural
reading, giving ~65–71 °C — but the units are `[INFERRED]` from context, not confirmed
against any datasheet. **Do not attempt to raise these.** Overriding a Li-ion
over-temperature cutoff is a safety question, not a software one.
