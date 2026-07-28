# USB console — an interactive root shell over the cable

**This is the answer to "can we control it directly over USB?": yes.** Not as a
UVC webcam (that path is dead), but as a **root serial console over the USB
cable**, with no soldering and no special client.

## Why this works `[VERIFIED-EXTRACTED]`

The firmware's USB gadget (managed by `deviced`,
`/usr/share/deviced/usb-configurations/usb-configurations.xml`) supports these
modes:

| mode | functions | what starts |
|---|---|---|
| 1 | mtp | mtp-responder |
| 2 | mtp,acm,sdb | mtp + sdbd + `serial-getty@ttyGS0` |
| **3** | **acm,sdb** | **sdbd + serial getty on ttyGS0** |
| 10 | mass_storage | (default — the USB "drive") |

Mode 3's gadget descriptor, verbatim: `funcs_fconf="acm,sdb"`, `idVendor 04e8`,
`idProduct 6860`, `iProduct SM-C200`. The **acm** function is a USB CDC-ACM
serial port — it appears on the device as `/dev/ttyGS0` and on the Mac as
`/dev/cu.usbmodem*`.

And the clincher: `/etc/passwd` is `root::0:0:root:/root:/bin/sh` — **root has
no password.** `agetty` on the device supports `--autologin root`, which drops
straight to a root shell with no login prompt at all (bypassing the `securetty`
case-mismatch where the device is `ttyGS0` but securetty lists `ttygs0`).

## What the card does (v11, `tools/card/rvf-start.sh`)

From the script-mode root shell it:
1. reconfigures the USB gadget to `acm,sdb` by writing the sysfs sequence
   deviced uses (`/sys/class/usb_mode/usb0/…`) — volatile, not a block-device
   write;
2. starts `agetty --autologin root` on `/dev/ttyGS0` (plus a raw `/bin/sh` bound
   to the serial as a backup, and `sdbd` for the sdb route);
3. sleeps to hold script mode open so the gadget stays up (dfmsd reboots on
   script exit, which would reset the gadget).

## How to use it

1. Write the card and run it as usual (insert into the AQK1 unit, power on).
2. Wait ~15 s for it to configure the gadget (watch nothing — it just sleeps).
3. **Plug the USB cable from the camera into the Mac.**
4. On the Mac:
   ```bash
   ls /dev/cu.usbmodem*
   screen /dev/cu.usbmodem<TAB> 115200      # Ctrl-A then K to quit
   ```
   A root shell prompt should appear (press Enter once if blank).

## Why this changes everything

Every attempt so far has fought the **insert-card → reboot → read** cycle: one
shot per boot, no feedback, script-mode only. A live USB root shell breaks that
open. With it we can:
- run commands interactively and see results immediately;
- from the live shell, make the USB mode persistent and reboot into **normal**
  mode (viewfinder running) with the console still attached;
- try the RVF trigger, a proper cross-compiled `gdb`, or anything else, live —
  instead of one card at a time.

## Unknowns to confirm on the bench `[UNKNOWN]`

- Whether macOS enumerates the Samsung `04e8:6860` ACM interface as a
  `/dev/cu.usbmodem*` (CDC-ACM is standard; it should). If not, the sdb route is
  the fallback (needs an `sdb` client).
- Whether dfmsd tolerates the script sleeping instead of exiting (it may have
  its own watchdog reboot). If the console dies after ~N seconds, that's why —
  and the next step is to set the USB mode persistently instead.
- Whether `/dev/ttyGS0` appears once the acm gadget is enabled (it should, from
  the g_serial/f_acm driver).
