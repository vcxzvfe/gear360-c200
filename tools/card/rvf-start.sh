#!/bin/sh
# rvf-start.sh (v11) -- bring up an interactive root shell over the USB cable.
#
# Big pivot. ptrace injection is a dead end (v1-v10). But the firmware's USB
# gadget supports a mode that exposes a CDC-ACM serial console AND sdb:
#   deviced usb-configurations.xml, mode 3 (acm,sdb):
#     funcs_fconf = "acm,sdb", idVendor 04e8, idProduct 6860, iProduct SM-C200
#   and /etc/passwd has root WITH NO PASSWORD (root::0:0:...).
#
# So this script (root, in script mode) reconfigures the USB gadget to acm,sdb
# and starts a PASSWORDLESS root shell on /dev/ttyGS0 via `agetty --autologin
# root` (bypassing login/securetty entirely). Then it sleeps to hold script
# mode open so the gadget stays up and dfmsd does not reboot.
#
# Result: plug the USB cable into the Mac and a /dev/cu.usbmodem* serial port
# appears; `screen /dev/cu.usbmodem... 115200` gives a live root shell. No
# soldering, no sdb client, no card-reboot cycle -- an INTERACTIVE shell at last.
#
# Writes only sysfs (volatile, reset by reboot; not a block device) and the SD
# card. No eMMC write.

OUT=/mnt/mmc/rvf-out
U=/sys/class/usb_mode/usb0
rm -f /mnt/mmc/info.tg 2>/dev/null; sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
log() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
log "STEP0: v11 USB-console; loop guard armed"
id > "$OUT/01-id.txt" 2>&1

# record the gadget's current state
{ echo "funcs_fconf=$(cat $U/funcs_fconf 2>&1)"
  echo "idProduct=$(cat $U/idProduct 2>&1)"
  ls -la /sys/class/usb_mode/ 2>&1; } > "$OUT/40-usb-before.txt"
sync
log "STEP1: usb0 exists? $( [ -d "$U" ] && echo yes || echo NO )"
if [ ! -d "$U" ]; then
    log "FATAL: /sys/class/usb_mode/usb0 missing; dumping /sys/class/usb_mode"
    ls -la /sys/class/usb_mode/ > "$OUT/41-usbmode-ls.txt" 2>&1; sync
    # keep alive anyway so we can inspect over... nothing. just exit.
    touch "$OUT/DONE"; sync; exit 1
fi

# --- switch gadget to mode 3 (acm,sdb), matching deviced's sysfs sequence ----
echo 0        > $U/enable            2>>"$OUT/00-stderr.txt"
echo 04e8     > $U/idVendor          2>>"$OUT/00-stderr.txt"
echo 6860     > $U/idProduct         2>>"$OUT/00-stderr.txt"
echo 0        > $U/bDeviceClass      2>/dev/null
echo 0        > $U/bDeviceSubClass   2>/dev/null
echo 0        > $U/bDeviceProtocol   2>/dev/null
echo acm,sdb  > $U/funcs_fconf       2>>"$OUT/00-stderr.txt"
echo null     > $U/funcs_sconf       2>/dev/null
echo SM-C200  > $U/iProduct          2>/dev/null
echo 1        > $U/enable            2>>"$OUT/00-stderr.txt"
sync
log "STEP2: gadget set -> funcs_fconf=$(cat $U/funcs_fconf 2>&1)"
sleep 2

# --- confirm the ACM serial node appeared -----------------------------------
ls -la /dev/ttyGS0 > "$OUT/42-ttyGS0.txt" 2>&1
log "STEP3: /dev/ttyGS0 -> $(ls -la /dev/ttyGS0 2>&1)"

# --- start sdbd too (root shell over sdb, for the sdb-client route) ----------
[ -x /usr/sbin/sdbd ] && { /usr/sbin/sdbd >/dev/null 2>&1 & log "STEP4: sdbd pid=$!"; }

# --- passwordless root shell on the USB serial (no login/securetty) ----------
if [ -c /dev/ttyGS0 ]; then
    /sbin/agetty --autologin root --keep-baud ttyGS0 115200,38400,9600 >/dev/null 2>&1 &
    log "STEP5: agetty --autologin root on ttyGS0, pid=$!"
    # fallback: a raw shell bound straight to the serial, in case agetty balks
    setsid sh -c 'exec /bin/sh <>/dev/ttyGS0 >&0 2>&1' >/dev/null 2>&1 &
    log "STEP5b: raw /bin/sh bound to ttyGS0 as backup, pid=$!"
else
    log "STEP5: /dev/ttyGS0 not a char device; ACM gadget may not have come up"
fi

log "STEP6: USB console should be live."
log "       On the Mac: plug the USB cable in, then:"
log "         ls /dev/cu.usbmodem*     (find the port)"
log "         screen /dev/cu.usbmodem<N> 115200   (root shell; Ctrl-A K to quit)"
log "       Holding script mode open so the gadget stays up. Power off when done."
touch "$OUT/DONE"; sync

# hold script mode so dfmsd does not reboot and reset the USB gadget
i=0
while [ $i -lt 1800 ]; do
    sleep 15; i=$((i+15))
    # heartbeat + keep re-asserting the shell if the serial dropped
    [ -c /dev/ttyGS0 ] && pgrep -f "agetty.*ttyGS0" >/dev/null 2>&1 || \
        { /sbin/agetty --autologin root --keep-baud ttyGS0 115200 >/dev/null 2>&1 & }
done
log "STEP7: 30-min keepalive elapsed; exiting (camera will reboot)"
