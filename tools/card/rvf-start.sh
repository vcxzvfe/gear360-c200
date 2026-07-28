#!/bin/sh
# rvf-start.sh (v13) -- stable, repeatable sdb-over-USB root shell.
#
# We have a reliable transport: in dfmsd script mode, set the USB gadget to
# acm,sdb and deviced+sdbd give a root shell over USB (tools/sdb_usb.py).
# Normal mode reverts to MTP (sdb_sel is volatile; the /sdcard/usb_test_mode.txt
# override is JIG-only), so the shell lives in script mode.
#
# Unlike v12 this does NOT delete info.tg -- so every power-on with this card in
# re-enters script mode and re-establishes the shell. This script does no
# injection, so it cannot crash the app; keeping info.tg is safe and makes the
# shell repeatable and crash-recoverable (a reboot just comes back to a shell).
#
# Writes: /opt vconf (persistent settings, ext4 data partition -- not firmware/
# rootfs), sysfs (volatile), SD card. No raw block / firmware write.

OUT=/mnt/mmc/rvf-out
U=/sys/class/usb_mode/usb0
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
log() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
log "STEP0: v13 stable sdb shell (info.tg kept for repeatability)"
id > "$OUT/01-id.txt" 2>&1

# enable sdb + select acm,sdb, and assert the gadget
vconftool set -t int memory/sysman/sdb_sel 1 -f 2>>"$OUT/00-stderr.txt"
vconftool set -t int db/usb/sel_mode        3 -f 2>>"$OUT/00-stderr.txt"
set_gadget() {
    echo 0        > $U/enable          2>/dev/null
    echo 04e8     > $U/idVendor         2>/dev/null
    echo 6860     > $U/idProduct        2>/dev/null
    echo acm,sdb  > $U/funcs_fconf      2>/dev/null
    echo null     > $U/funcs_sconf      2>/dev/null
    echo SM-C200  > $U/iProduct         2>/dev/null
    echo 1        > $U/enable           2>/dev/null
}
[ -d "$U" ] && set_gadget
[ -x /usr/sbin/sdbd ] && { /usr/sbin/sdbd >/dev/null 2>&1 & }
log "STEP1: sdb up. funcs=$(cat $U/funcs_fconf 2>&1). Plug USB, then unplug/replug once."
log "       Mac: python3 tools/sdb_usb.py   (root shell)"
touch "$OUT/DONE"; sync

# hold script mode; keep re-asserting the gadget so a deviced clobber loses.
while true; do
    sleep 5
    [ -d "$U" ] && [ "$(cat $U/funcs_fconf 2>/dev/null)" != "acm,sdb" ] && set_gadget
done
