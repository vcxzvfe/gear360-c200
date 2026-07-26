# SM-C200 Shell Procedure

**Read `03-safety-and-recovery.md` before executing anything here.**

This document is split deliberately:

- **Part A — NON-PERSISTENT.** SD card only. Root filesystem untouched. Reversible by
  removing one file. **Every documented C200 brick came from leaving this path.**
- **Part B — PERSISTENT.** Writes to the root filesystem and rebuilds the hibernate
  snapshot. This is where hardware dies. Single-author, unreplicated.

**Do not read Part B until Part A has answered everything it can.**

---

# PART A — NON-PERSISTENT ROOT SHELL (do this one)

## A.0 What this gives you

Root shell on the camera while the SD card is inserted. Remove `info.tg` and the camera
boots normally, unmodified. Nothing is written to internal storage.

`[COMMUNITY, 4 independent C200 reports]` The mechanism works on the SM-C200 and was
never patched, including on the final firmware.

## A.1 Bill of materials

### microSD card

| Item | Spec | Confidence |
|---|---|---|
| Max capacity accepted | **200 GB** | `[VERIFIED]` — official SM-C200 manual |
| Recommended size for this work | **8–32 GB** | `[INFERRED]` — small = fast to reformat; capacity is irrelevant here |
| Filesystem | **FAT32** | `[COMMUNITY]` — *not* stated in Samsung's manual. Safest option: **format the card in the camera first**, then add files from the Mac. |
| Speed class | Irrelevant for scripting | `[INFERRED]` — manual only warns slow cards interrupt *video recording* |
| Quantity | **Two** | Keep an identical spare prepared as a rescue card |

> `[UNKNOWN]` Whether the C200 accepts exFAT. Do not assume. Format in-camera.

### Files on the SD card root

**Copy these files. Do not retype them.** `[VERIFIED, byte-level]` Both known-good `.adj`
files contain a **trailing space** before the newline, and one `info.tg` has **two**
newlines. Retyping loses these silently.

Two known-good variants exist. Both work on C200.

**Variant 1 — LalaTheDog lineage** (`[VERIFIED]` 11 / 35 bytes):

```
info.tg      "nx_cs.adj\n\n"                        ← 11 bytes, TWO newlines
nx_cs.adj    "shell script /mnt/mmc/<script>.sh \n" ← trailing SPACE before \n
<script>.sh  your payload
```

**Variant 2 — lansysart lineage** (`[VERIFIED]` 18 / 31 / 0 bytes):

```
info.tg      "nx_ft.adj\ndfms.tg\n"                 ← 18 bytes
nx_ft.adj    "shell script /mnt/mmc/<script>.sh \n" ← trailing SPACE before \n
dfms.tg      (empty, 0 bytes)
<script>.sh  your payload
```

`[UNKNOWN]` What `dfms.tg` does. It appears in no NX documentation and I could not find it
in the C200 firmware image. Hypothesis (untested): it suppresses the test-mode overlay.
**This is the cleanest A/B experiment available** — see Experiment 6.

`[VERIFIED — from Samsung's own factory text inside the C200 firmware]` The `.adj`
filename is **arbitrary**; `info.tg` names it. Samsung's own example is
`paf_adj_restore.adj`. So `nx_cs.adj` vs `nx_ft.adj` is not a meaningful distinction —
what matters is that `info.tg` names the file that exists.

`[CORRECTED]` A claim circulates that the payload script must be named `test.sh`. This is
folklore. The full path is inside the `.adj` file, and the two working C200 packages use
`upgrader.sh` and `mods.sh`.

### Binaries (only needed once you want network access)

`[VERIFIED, by me — `file` + `md5`]` The busybox shipped in the working C200 mod package:

```
telnetd / httpd / ftpd / tcpsvd
  → all four are THE SAME FILE, md5 96ff4db8d1237f68d5c8079b1d262120
  → 2,003,944 bytes
  → ELF 32-bit LSB executable, ARM, EABI5, statically linked, stripped
  → BusyBox v1.18.4 (2011-03-30 08:58:44 KST)
```

It is a **multi-call busybox**: it decides what to be from `argv[0]`, which is why four
identically-named copies exist. Source:
https://github.com/lansysart/gear360-telnet.usbshell-mod

**Cross-compilation rules if you build your own** `[COMMUNITY]`:
- **Static ARM EABI5 works.** This is the safe choice.
- If linking dynamically you must use **soft-float `gnueabi`, NOT `gnueabihf`** — a
  hard-float binary containing only `return 0;` reportedly **powers the camera off
  instantly**. Use `-Wl,-dynamic-linker,/lib/ld-2.13.so`.
- `[COMMUNITY]` Transfer binaries in **binary mode**; ASCII-mode FTP silently corrupts them.
- `[VERIFIED]` Samsung's own C200 open-source release ships the matching toolchain
  (CodeSourcery `arm-2010q1`): https://github.com/KieronQuinn/Gear360_OSS

### Firmware image (keep offline, do not put on the card yet)

```
C200GLU0AQK1_171121_1257_REV00_user.bin
  279,094,189 bytes
  SHA256 150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db
```

`[VERIFIED, by me]` This is your only recovery image and every Samsung host is dead. Keep
**two offline copies**. See `03-safety-and-recovery.md` for verification.

---

## A.2 Stage 1 — Proof of execution (read-only, safest possible first step)

**Goal:** prove the chain runs on *your* camera before you trust it with anything.

This script only **reads** the device and **writes to the SD card**. It touches nothing
internal.

`recon.sh`:

```sh
#!/bin/sh
# C200 read-only reconnaissance. Writes only to /mnt/mmc (the SD card).
export PATH="/usr/share/scripts:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

OUT=/mnt/mmc/recon.txt
echo "=== recon $(date '+%Y%m%d%H%M%S') ===" > $OUT

echo "--- id / uname ---"        >> $OUT
id                                >> $OUT 2>&1
uname -a                          >> $OUT 2>&1

echo "--- PATH as inherited ---" >> $OUT
echo "$PATH"                      >> $OUT 2>&1

echo "--- firmware version ---"  >> $OUT
cat /etc/version.info             >> $OUT 2>&1

echo "--- cpuinfo ---"           >> $OUT
cat /proc/cpuinfo                 >> $OUT 2>&1

echo "--- mounts ---"            >> $OUT
mount                             >> $OUT 2>&1

echo "--- /usr/bin listing ---"  >> $OUT
ls -l /usr/bin                    >> $OUT 2>&1

echo "--- video/media devices ---" >> $OUT
ls -l /dev/video* /dev/d5_* 2>&1  >> $OUT

echo "--- network ---"           >> $OUT
ifconfig -a                       >> $OUT 2>&1

echo "=== done ===" >> $OUT
sync
sync
sync
```

**Card layout:**

```
/info.tg          (copied, byte-exact)
/nx_cs.adj        (copied, edited to say: shell script /mnt/mmc/recon.sh )
/recon.sh         (above)
```

> **The one edit you must make correctly:** the `.adj` file must name *your* script.
> Edit only the filename portion; **preserve the trailing space and the newline**.

**Procedure:**
1. Camera **off**, battery charged.
2. Insert the prepared card.
3. Power on. Expect the factory/test UI (green dots / test menu) — this is normal and
   means `dfmsd` started.
4. Wait ~60 s.
5. Power off, remove card, read `recon.txt` on the Mac.

**Success:** `recon.txt` exists and contains your `id` output as `uid=0(root)`.

**Failure — nothing written:** the chain did not fire. Check byte-exactness of `info.tg`
and the `.adj` (especially the trailing space), and that the `.adj` names the right script.

**Reversal:** delete `info.tg` from the card. **`[VERIFIED]`** Removing that one file exits
test mode; nothing on the camera was changed.

### `[UNKNOWN]` gaps at this stage

- Whether your firmware's inherited `PATH` includes `/usr/sbin`. That is why the script
  logs it — the answer determines whether later scripts need absolute paths.
- Whether `/dev/video*` exists at all. **Nobody has ever posted an `ls /dev` from a C200.**
  The script above answers this in one shot; it is a genuine contribution.

---

## A.3 Stage 2 — Network access (still non-persistent)

Once Stage 1 proves execution, add telnet. Still SD-only; still reversible.

> **`[VERIFIED]` HAZARD — do not run the shipped `mods.sh` or `G360POWE_G360POW.sh`
> unmodified.** Two independent problems:
>
> 1. **It hijacks `wlan0` onto your home WLAN** with a static IP (`192.168.0.22`) via
>    `wpa_supplicant`. The camera's own RVF stack uses **Wi-Fi Direct (`p2p0`,
>    192.168.49.10)** or its **SoftAP (192.168.107.1)**. `[INFERRED]` Running both is an
>    unresolved conflict and is the single most likely thing to block the live-video goal.
> 2. **`G360POWE_G360POW.sh` contains `st cap capdtm setusr` commands copy-pasted from the
>    NX/R210 documentation** — complete with comments listing camera modes
>    (`aperture / shutter / manual / imode / magic / scene`) that a Gear 360 does not have.
>    I traced the identical text to `gear360_modding/README.md` (R210) and
>    `nx500_nx1_modding/ST Commands.md` (NX). **These write factory user-data on your C200
>    using another camera's ID table.** Delete those lines.
>
> Also `[VERIFIED]`: that same file has a **typo that breaks the web server** —
> `-h /mnt/mmcmods/www/` (missing slash) instead of `/mnt/mmc/mods/www/`. The correct
> form is in `mods.sh` in the same repo.

**Minimal telnet script** — no Wi-Fi reconfiguration, no `capdtm`:

```sh
#!/bin/sh
export PATH="/usr/share/scripts:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
/mnt/mmc/mods/telnetd &
```

`[UNKNOWN]` **This minimal form is untested.** Every published C200 recipe brings up
networking itself, because in factory mode the camera may not have any interface up. If
telnet is unreachable, you must bring an interface up — and at that point you must decide
between the camera's own Wi-Fi (needed for RVF) and your home WLAN (convenient for shell).
**They may be mutually exclusive.** This is Experiment 8.

Connect: `telnet <camera-ip>`, log in as `root`, **no password** `[VERIFIED]`.

### Known-working `st` verbs on C200

| Command | Status |
|---|---|
| `st led N on` / `off` / `blink` | `[COMMUNITY]` works (N: 0=red, 1=green, 2=blue, 3=rear, 4=front) |
| `st log sound` | `[COMMUNITY]` used in shipped C200 script |
| `st app nx capture single` | `[COMMUNITY]` **REBOOTS the C200.** Do not run. |
| `st cap capdtm setusr …` | **`[CORRECTED]` NOT demonstrated on C200.** Every example traces to R210/NX. The one C200 owner who asked got no reply. |
| Any streaming verb | `[UNKNOWN]` — none documented, none found |

`[COMMUNITY]` Note the `st` binary used for the LED work was taken from the **NX1/NX500**
modding repo, not necessarily the stock one — though `st` does exist on the stock C200.

---

## A.4 What Part A cannot do

- Nothing survives a reboot without the card.
- `[COMMUNITY]` In factory/test mode the normal camera app behaves differently. `dfmsd`
  overlays a test UI. **`[UNKNOWN]`** whether the RVF/live-video stack is fully functional
  in factory mode — this matters enormously for the project and is Experiment 7.

**This is the boundary. Everything past here can destroy the camera.**

---

# PART B — PERSISTENT ROOT (danger)

**Do not enter Part B to satisfy curiosity.** Enter it only if Part A has proven that a
persistent hook is genuinely required.

## B.0 Why this is dangerous

`[COMMUNITY]` The C200 resumes from a **hibernation snapshot** rather than cold-booting.
An edited root filesystem paired with a stale snapshot is inconsistent, and that
inconsistency is how every documented C200 rootfs brick happened.

> *"first attempt to change root filesystems resulted in filesystem corruption … Not
> writing the details here since this step is quite risky."* — usumfabricae, SM-C200

**Public success rate for the repair is roughly 1 in 3.** Two C200 owners entered an
infinite restart loop and were **never recovered**.

## B.1 The only published safe-write sequence

`[COMMUNITY]` kjuanman's 12 steps, quoted with his own warning intact:

> **Warning, Danger: this can brick your camera. You are modifying your internal root
> read only filesystem and is very easy to get corrupted**
>
> 1. Login in telnet in factory mode
> 2. `mount -o remount,rw /`
> 3. edit some files
> 4. `sync;sync;sync`
> 5. `mount -o remount,ro /`
> 6. `/usr/bin/erase_snapshot.sh`
> 7. Wait after reboot
> 8. Login in telnet in factory mode
> 9. `/usr/bin/make_snapshot.sh`
> 10. Wait after reboot
> 11. Power off camera
> 12. You can `mv info.tg` and boot normally

**Step 2 is the first irreversible action in this entire project.**

`[COMMUNITY]` After `make_snapshot.sh`, **wait 3–5 minutes without pressing anything**.
lansysart's warning: *"Wait for snapshot process to complete! Do not POWER OFF, or Push
any button."*

`[COMMUNITY]` Always `cp <file> <file>.backup` **before** editing anything.

`[UNKNOWN]` Why the repair works for some and not others. The scripts' contents have never
been published, and preconditions (free space, battery level, SD present) are unknown.

## B.2 Hook points

| Path | Status |
|---|---|
| `/usr/lib/systemd/system/factory_check.sh` | `[COMMUNITY, C200]` used successfully |
| `/usr/bin/deviced-pre.sh` | `[COMMUNITY, C200]` used by the 2026 mod |
| `/usr/mod/factory_check_script.sh` | **`[CORRECTED]` NOT a hook.** Appears in the record only as the *symptom* of corruption (unreadable inode). |
| `/usr/mod/autostart_script.sh` | **`[CORRECTED]` same — not demonstrated as a hook** |
| `/usr/sbin/bluetoothd` (NX method) | **`[VERIFIED]` CORRUPTS the C200.** NX-only. Never do this. |

`[COMMUNITY]` `/opt/usr` has free space and is a separate partition — a better place for
your own files than `/`.

## B.3 The 2026 persistent recipe

https://github.com/lansysart/gear360-telnet.usbshell-mod

Appends a debug hook to `/usr/bin/deviced-pre.sh`, installs a systemd unit, rebuilds the
snapshot. Yields telnet in **normal** boot (not factory mode) plus FTP and an HTTP mod
interface on 8888, and can expose a USB ACM serial console via
`echo "acm" > /sys/class/usb_mode/usb0/funcs_fconf`.

**`[CORRECTED]` Weight this honestly:**
- **One author, zero independent confirmations.**
- His own first message: *"i have brick one of my device, but i have shell."*
- `[VERIFIED]` The USB console is conditional: *"only if SDCard not installed"*.
- `[VERIFIED]` The USB console is a **software USB-gadget** (`/dev/ttyGS0`), **not a
  hardware UART**. It only exists after Linux has booted, so it is **useless for
  recovering a non-booting camera.**
- `[VERIFIED]` His README's file list for the firmware flash (`updater.adj`, `updater.sh`)
  **does not match** the repo he links, which contains `nx_cs.adj` and `upgrader.sh`. Do
  not use his list as a shopping list.

## B.4 `[UNKNOWN]` gaps in Part B

- Whether `deviced-pre.sh` persistence conflicts with the camera app's normal startup.
- Whether the persistent Wi-Fi-station configuration can coexist with RVF (Experiment 8).
- What `/usr/bin/system-recovery` does. It appears in a real C200 `/usr/bin` listing and
  **nobody has ever investigated it.** It could be a fourth recovery tier.

---

## Appendix — three incompatible "C200 SD flash" file sets in circulation

`[VERIFIED]` These all claim to flash a C200 and they disagree. Know which you are using.

| Source | Files |
|---|---|
| LalaTheDog (repo contents, byte-verified) | `.bin` + `info.tg` (11 B) + `nx_cs.adj` (35 B) + `upgrader.sh` (516 B) |
| lansysart README (**does not match the repo it cites**) | `.bin` + `info.tg` (12 B) + `updater.adj` (33 B) + `updater.sh` (123 B) |
| Andy2000 / KieronQuinn "Option 2" | `.bin` + `updater.sh` only — **no `info.tg`, no `.adj`** |

`[COMMUNITY]` An XDA user reported the two-file method **did not work** on a 2016 model
and had to be redirected to a different procedure.

**Recommendation `[INFERRED]`:** use the LalaTheDog repo's *actual files*, because those
are the only ones I verified byte-for-byte and they are internally consistent with the
mechanism documented in Samsung's own embedded factory text.

`[VERIFIED]` Harmless oddity in LalaTheDog's `upgrader.sh`: line 2 is
`/dev/event0 /dev/event1 &` with no command in front — a `keyscan` invocation with the
program name stripped out. It will fail to execute and is backgrounded, so it is inert
noise, not a hazard. It is the fossil of the removed button-trigger.
