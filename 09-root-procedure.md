# SD-card root procedure — SM-C200

**Status: ready for the zero-risk reconnaissance stage (Stage A). The RVF trigger itself (Stage B)
is now fully designed in [`10-rvf-trigger.md`](10-rvf-trigger.md) — command id 20 = `EXE_LIVEVIEW`
via an in-process ptrace call; the one open gate is whether Tizen SMACK permits root ptrace, which
the card run records read-only.**

Everything here was read directly out of the extracted root filesystem and the stock
example files, not inferred. Evidence tags: `[VERIFIED-EXTRACTED]` (read from the camera's
own binaries/files), `[COMMUNITY]`, `[INFERRED]`, `[UNKNOWN]`.

---

## The mechanism, confirmed from three independent sources

`[VERIFIED-EXTRACTED]` `/usr/bin/dfmsd` reads `/sdcard/info.tg` with `fopen`/`fgets`; that
file names an `.adj` file; the `.adj` file contains a DFMS command; the `shell script`
verb runs a shell script. The three stock/community examples on disk agree exactly:

| File | Stock updater (archive.org) | Community SD-root example |
|---|---|---|
| `info.tg` | `updater.adj\n` | `nx_cs.adj\n` |
| `.adj` | `shell script /mnt/mmc/updater.sh\n` | `shell script /mnt/mmc/test.sh\n` |
| `.sh` | **a firmware flash** ⚠ | starts `telnetd` + `httpd` |

`[VERIFIED-EXTRACTED]` So the `.adj` grammar is literally `shell script <absolute-path>`.
The `.adj` filename itself is arbitrary — `info.tg` names it. `/sdcard` → `/mnt/mmc` →
`/opt/storage/sdcard` are the same directory (the SD card), so `/mnt/mmc/...` in the `.adj`
and `.sh` is correct.

**The stock `updater.sh` is a firmware flash** (`fw_upgrade_start` on a `C200*.bin`). We do
not reproduce it. Our `.sh` writes to no block device.

### Byte-exactness

`[VERIFIED-EXTRACTED]` The stock files end in a single `\n` with no trailing space (verified
by hexdump: `info.tg` = `updater.adj\x0a`, `.adj` = `...updater.sh\x0a`). Match that: one
trailing newline, no trailing space, no CRLF. Write the card on the Mac so line endings stay
LF.

---

## ⚠ Card safety rules — read before writing the card

`[VERIFIED-EXTRACTED]` from the firmware teardown (`08-firmware-teardown.md` §2.3):

1. **Zero files whose name begins `C200`.** Any such file is a firmware candidate, the model
   string is *not* validated, and it would be flashed. This includes a stray
   `C200GLU0AQK1_...bin` or any half-copied `.part`.
2. **Zero `.bin` files, zero firmware-shaped files, of any name.**
3. The card is **FAT32**.
4. The `.sh` touches **no block device** — no `dd`, no `mount`, no `fw_upgrade*`, no writes
   to `/dev/mmcblk*`. Verify every line.
5. **Guinea pig is the AQK1 unit.** The APC9 unit is not involved in any way — it has no
   recovery image and must never receive a card mod that could persist.

---

## Stage A — read-only reconnaissance (zero network, zero risk)

The insight that makes this safe: **the first pass needs no interactive shell at all.** The
`.adj` runs a batch script that writes read-only findings to the SD card. Power off, move
the card to the Mac, read the results. No network to configure, no foreign binary on the
card, nothing written to the camera.

`[VERIFIED-EXTRACTED]` Every tool the script uses is present on the device: `/bin/netstat`,
`/bin/ps`, `/bin/mount`, `/usr/bin/id`, `/bin/uname`, `/usr/bin/dbus-send`,
`/usr/bin/systemctl`, `/usr/sbin/ss`, `/usr/bin/st`, `/bin/cat`, `/bin/ls`.

### Card contents for Stage A

Three files at the card root. `<ADJ>` can be any name not beginning `C200`; this procedure
uses `recon.adj`.

`info.tg` (exactly, one trailing newline):
```
recon.adj
```

`recon.adj` (exactly, one trailing newline):
```
shell script /mnt/mmc/recon.sh
```

`recon.sh` — see [`tools/card/recon.sh`](tools/card/recon.sh). It runs a fixed list of
read-only commands and tees them to `/mnt/mmc/recon-out/`. It writes only to the SD card,
never to a block device on the camera. It ends by touching a `DONE` marker so you can tell
completion from a hang.

### Running Stage A

`[COMMUNITY]` + `[INFERRED]` — the activation gesture is community-reported and consistent
with the `dfmsd` script-mode design, but the exact button/LED sequence was **not** recoverable
from the firmware and should be treated as `[UNKNOWN]` until you see it on the bench:

1. Write the three files to a FAT32 microSD. Re-check the safety rules above.
2. Insert the card into the **AQK1** unit, powered off.
3. Power on. `[COMMUNITY]` A short blue LED above the power key indicates it read the card.
4. `[COMMUNITY]` Double-click the Menu/Power key; a green→orange→green cycle indicates
   script mode fired. **If your unit's gesture differs, stop and report what you see** — do
   not improvise repeated button presses.
5. Wait ~60 s. Power off (hold power). Move the card to the Mac.
6. Read `recon-out/`. The presence of `recon-out/DONE` means the script completed; its
   absence means the chain did not fire — re-check `info.tg`/`.adj` byte-exactness first.

### What Stage A answers (all previously unknown for a C200)

- `netstat -lntp` **in whatever mode the camera is in** — settles which process owns 80,
  7676, 7679, 9001, confirming or refuting the teardown's single-process finding on real
  hardware.
- `ls -la /dev/video*` — does a V4L2 capture node exist. This decides whether the non-RVF
  capture path (§4 of the teardown) is even reachable.
- `id` — confirms root.
- `cat /etc/version.info` — the exact build, from inside.
- `st` verb enumeration and a **read** of the current wifi-mode userdata (no write).
- `ps`, `mount`, `systemctl list-units` — the running process/service picture.
- `dbus-send --print-reply` introspection of `org.bt.app` — the injection surface for the
  RVF trigger, read-only.

**Reversal:** delete `info.tg` from the card. `[VERIFIED-EXTRACTED]` Nothing was written to
the camera; Stage A leaves no persistent change.

---

## Stage B — interactive shell (one open transport question)

The whole RVF trigger is now scripted (B3 below → [`10-rvf-trigger.md`](10-rvf-trigger.md)); an
interactive shell is a convenience on top of that, not a prerequisite. Here is the honest state of
the (interactive-shell) transports:

`[VERIFIED-EXTRACTED]` The rootfs has **no** `telnetd`, `busybox`, `dropbear`, `nc`,
`socat`, `ncat`, or on-device `python`/`perl`. So a network shell needs *something* brought
onto the card. Options, best first:

**B1 — `sdbd` (the camera's own debug bridge), the clean option in principle.**
`[VERIFIED-EXTRACTED]` `/usr/sbin/sdbd` exists; it reads the TCP port from key
`service.sdb.tcp.port` and logs `tcp:%d`. A `.sh` could `systemctl start sdbd` or run it
directly, and — if it listens on TCP — the Mac connects over Wi-Fi.
- **Blocker `[UNKNOWN]`:** whether `sdbd` binds TCP by default or only USB, and the Mac has
  **no `sdb` client** (that is a Tizen-SDK tool; `adb` does **not** speak the sdb protocol).
  Installing Tizen Studio just for this is heavy. **Verify on the bench with Stage A first:**
  have `recon.sh` run `sdbd` and then `netstat -lntp`, and read from the output whether a
  TCP port (commonly 26101) appears. Only then decide if B1 is worth pursuing.

**B2 — a static ARM `busybox` on the card, the community route.** `[COMMUNITY]` The
SD-root example ships `/mnt/mmc/telnetd` + `httpd` and the `.sh` starts them. This is proven
to work but means **placing a foreign binary on the card**. If used, it must be a `busybox`
built for this SoC's ABI (ARMv7 soft/hard-float — confirm against a rootfs binary with
`file`), and it is not firmware-shaped so it does not trip the flash rule. Keep it out of
scope until Stage A confirms the ABI and the network situation.

**B3 — no interactive shell; batch the RVF trigger directly. This is the plan, and it is now
fully worked out in [`10-rvf-trigger.md`](10-rvf-trigger.md).** The whole goal reduces to "make
`di-camera-app` enter RVF," and the teardown pinned exactly how: command id **20 =
`EXE_LIVEVIEW`** driven into the app's own dispatcher. The earlier guesses in this bullet (emit on
D-Bus `org.bt.app_event`, or call `DlnaRVF_ML_FJ_Start`) turned out to be **dead or fragile** —
`[VERIFIED-BY-OBJDUMP]` the `app_event` signal carries only connection state, and the command path
lives entirely in-process (fed by SAP/RFCOMM from the phone). So the trigger is an **in-process
ptrace call** — `btSendEventToUI(8,0,20,0)`, the phone's exact call — made by a small static ARM
injector (`tools/card/rvf-inject.c`) that the card script (`tools/card/rvf-start.sh`) stages into
tmpfs and fires, then proves 7679 with `netstat`. It writes no block device and reverts the call
before exit. **The one open gate is whether Tizen SMACK permits root ptrace; the card run answers
that read-only.** See `10-rvf-trigger.md` §1 (the answer), §3 (fallbacks F1–F4), §5 (the ptrace/SMACK
unknown).

**Recommendation:** run Stage A to settle B1 vs B2 (network shell) and confirm the port picture,
then run the Stage-B card set from `10-rvf-trigger.md` (B3) — that is the actual RVF trigger and
the most likely first success. Do not put a network-shell binary (B2) on the card until Stage A has
run; the RVF injector (B3) is a separate, purpose-built helper and is the point of the exercise.

---

## What is still UNKNOWN, and how to settle it safely

1. **The exact activation gesture.** `[UNKNOWN]` from firmware. Settle by observing the LEDs
   on the first Stage-A attempt; the card change is reversible, so a non-firing attempt costs
   nothing.
2. **Whether `sdbd` offers TCP.** `[UNKNOWN]`. Stage A's `netstat` answers it read-only.
3. **The RVF trigger encoding.** *Resolved* — see [`10-rvf-trigger.md`](10-rvf-trigger.md).
   Command id **20 = `EXE_LIVEVIEW`**, delivered in-process via `btSendEventToUI(8,0,20,0)`. The
   D-Bus `org.bt.app_event` route once guessed here is `[VERIFIED-BY-OBJDUMP]` **dead** (state
   signals only). The remaining open item is not the encoding but whether Tizen SMACK permits root
   `ptrace` for the injector — the Stage-B card run records that from the injector's own stderr.

None of these require writing to the camera to answer. Run Stage A, read the card, decide
the next batch from evidence.
