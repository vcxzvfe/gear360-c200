#!/bin/sh
# rvf-start.sh (v12) -- make deviced bring up acm,sdb over USB (not MTP).
#
# v11 proved the USB path works: the camera enumerated on the Mac as Samsung
# 04e8:6860. BUT it came up as PTP/MTP (interface class 6), not acm,sdb --
# because on USB connect, deviced sets the mode from the persistent selector
# `db/usb/sel_mode`, which is 1 (mtp), clobbering the gadget we had set.
#
# v12 doesn't fight deviced; it sets the persistent selector to 3 (acm,sdb) and
# enables sdb, so deviced ITSELF brings up acm,sdb when the cable is (re)plugged.
# It also directly re-asserts the gadget in a loop as a backup, and holds script
# mode open. Then the Mac talks sdb over USB with tools/sdb_usb.py (no Tizen
# Studio, no serial driver needed -- macOS leaves the vendor interface free for
# libusb).
#
# Writes: the vconf DB under /opt (ext4 data partition -- persistent settings,
# reversible, NOT the firmware/rootfs eMMC), sysfs (volatile), and the SD card.
# No raw block-device / firmware write.

OUT=/mnt/mmc/rvf-out
U=/sys/class/usb_mode/usb0
rm -f /mnt/mmc/info.tg 2>/dev/null; sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
log() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
log "STEP0: v12 -- set persistent USB mode 3 (acm,sdb) so deviced brings up sdb"
id > "$OUT/01-id.txt" 2>&1

# record current selectors for the record
{ echo "db/usb/sel_mode (before):"; vconftool get db/usb/sel_mode 2>&1
  echo "memory/sysman/sdb_sel (before):"; vconftool get memory/sysman/sdb_sel 2>&1
  echo "raw sel_mode file:"; xxd /opt/var/kdb/db/usb/sel_mode 2>&1; } > "$OUT/50-sel-before.txt"
sync

# 1) enable sdb + select mode 3 (acm,sdb), persistently
vconftool set -t int memory/sysman/sdb_sel 1 -f  2>>"$OUT/00-stderr.txt"
vconftool set -t int db/usb/sel_mode        3 -f  2>>"$OUT/00-stderr.txt"
vconftool set -t int db/setting/usb_mode    3 -f  2>>"$OUT/00-stderr.txt"
sync
{ echo "db/usb/sel_mode (after):"; vconftool get db/usb/sel_mode 2>&1
  echo "sdb_sel (after):"; vconftool get memory/sysman/sdb_sel 2>&1; } > "$OUT/51-sel-after.txt"
sync
log "STEP1: selectors set -> sel_mode=$(vconftool get db/usb/sel_mode 2>&1 | tr -d '\n')"

# 2) also assert the gadget directly, now and in a loop, as a backup in case
#    deviced does not re-apply on its own.
set_gadget() {
    echo 0        > $U/enable          2>/dev/null
    echo 04e8     > $U/idVendor         2>/dev/null
    echo 6860     > $U/idProduct        2>/dev/null
    echo acm,sdb  > $U/funcs_fconf      2>/dev/null
    echo null     > $U/funcs_sconf      2>/dev/null
    echo SM-C200  > $U/iProduct         2>/dev/null
    echo 1        > $U/enable           2>/dev/null
}
[ -d "$U" ] && { set_gadget; log "STEP2: gadget set -> funcs=$(cat $U/funcs_fconf 2>&1)"; } \
            || log "STEP2: $U missing"

# 3) start sdbd directly too (in case deviced does not)
[ -x /usr/sbin/sdbd ] && { /usr/sbin/sdbd >/dev/null 2>&1 & log "STEP3: sdbd pid=$!"; }

log "STEP4: ready. On the Mac:"
log "       1) UNPLUG then REPLUG the USB cable (so deviced re-applies mode 3)"
log "       2) python3 ~/Dev/claude/gear360-c200/tools/sdb_usb.py --probe"
log "          -> should show a vendor(0xff) interface with a bulk pair (=sdb)"
log "       3) python3 ~/Dev/claude/gear360-c200/tools/sdb_usb.py   (root shell)"
touch "$OUT/DONE"; sync

# hold script mode; keep re-asserting the gadget so a deviced clobber loses
i=0
while [ $i -lt 1800 ]; do
    sleep 5; i=$((i+5))
    [ -d "$U" ] && [ "$(cat $U/funcs_fconf 2>/dev/null)" != "acm,sdb" ] && set_gadget
done
log "STEP5: keepalive elapsed; exiting"
