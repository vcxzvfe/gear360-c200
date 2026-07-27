#!/bin/sh
# rvf-start.sh -- Stage-B RVF trigger for the SM-C200, run by dfmsd script mode.
#
# Driven by info.tg -> rvf.adj ("shell script /mnt/mmc/rvf-start.sh").
#
# Goal: from root, make the running di-camera-app enter Remote View Finder so it
# binds the HEVC stream on TCP 7679 (and the RVF streaming/UPnP port 7676) with
# NO phone. Then prove it with netstat and leave the results on the SD card.
#
# It writes ONLY to the SD card (/mnt/mmc/rvf-out) and to tmpfs (/tmp, RAM). It
# touches NO block device on the camera: no dd, no mount, no fw_upgrade, no write
# to /dev/mmcblk*. The only "action" is an in-process ptrace call that is fully
# reverted before this script exits (see rvf-inject.c).
#
# The trigger value is proven: command id 20 = EXE_LIVEVIEW starts RVF (see
# 10-rvf-trigger.md). We try two in-process call sites, both with id 20, and
# check 7679 after each. We stop at the first that works.
#
# Read tools/card/README.md and 10-rvf-trigger.md before using this.

OUT=/mnt/mmc/rvf-out
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"

LOG="$OUT/00-log.txt"
say() { echo "$@" | tee -a "$LOG"; }
rule() { say "----------------------------------------------------------------"; }

say "### rvf-start.sh  (SM-C200 RVF trigger, id=20 EXE_LIVEVIEW)"
say "### clock is unset on this device; timing is relative only"
id | tee "$OUT/01-id.txt" >>"$LOG"
rule

# --- baseline: is 7679 already up? -------------------------------------------
netstat -lntp > "$OUT/02-netstat-before.txt" 2>&1
if grep -q ':7679' "$OUT/02-netstat-before.txt"; then
    say "NOTE: 7679 already listening before we did anything (RVF already active?)."
fi

# --- locate the target process ------------------------------------------------
PID=$(pidof di-camera-app 2>/dev/null)
[ -z "$PID" ] && PID=$(ps 2>/dev/null | awk '/di-camera-app/ && !/awk/ {print $1; exit}')
if [ -z "$PID" ]; then
    say "FATAL: di-camera-app is not running; nothing to inject into."
    touch "$OUT/DONE"; exit 1
fi
say "di-camera-app pid = $PID"
cp "/proc/$PID/maps" "$OUT/03-maps.txt" 2>/dev/null
cat "/proc/$PID/attr/current" > "$OUT/04-target-smacklabel.txt" 2>/dev/null

# --- best-effort: relax ptrace gating (yama + SMACK) --------------------------
# As root this is usually unnecessary, but Tizen's SMACK can still block ptrace.
echo 0 > /proc/sys/kernel/yama/ptrace_scope 2>/dev/null
# Match our SMACK label to the target's (falls back silently if not permitted).
TGT_LABEL=$(cat "/proc/$PID/attr/current" 2>/dev/null)
[ -n "$TGT_LABEL" ] && echo -n "$TGT_LABEL" > /proc/self/attr/current 2>/dev/null
cat /proc/self/attr/current > "$OUT/05-our-smacklabel.txt" 2>/dev/null

# --- stage the injector into an exec-capable tmpfs ---------------------------
# The FAT32 card is typically mounted noexec, so copy to RAM and run from there.
INJ=""
for d in /tmp /run /dev/shm /opt/usr/tmp; do
    [ -d "$d" ] || continue
    cp /mnt/mmc/rvf-inject "$d/rvf-inject" 2>/dev/null || continue
    chmod 0755 "$d/rvf-inject" 2>/dev/null
    # smoke test: with no args the injector prints usage and exits 2. If we get
    # exit 2, the dir is exec-capable; anything else (126/127) means noexec -> try next.
    "$d/rvf-inject" >/dev/null 2>&1
    if [ $? -eq 2 ]; then INJ="$d/rvf-inject"; break; fi
    rm -f "$d/rvf-inject" 2>/dev/null
done
if [ -z "$INJ" ]; then
    say "FATAL: could not stage rvf-inject into an exec-capable dir."
    say "       (is /mnt/mmc/rvf-inject present on the card? is /tmp execable?)"
    touch "$OUT/DONE"; exit 1
fi
say "injector staged at $INJ"

# --- helper: check whether 7679 is now listening -----------------------------
up7679() { netstat -lntp 2>/dev/null | grep -q ':7679'; }

WINNER="none"

# =============================================================================
# Candidate 1 (primary): btSendEventToUI(8, 0, 20, 0) in libdi-network-bt-app.
# This is byte-for-byte the call the phone's execute-liveview causes. THUMB.
# func = <runtime base of the .so> + 0x8de0.
# =============================================================================
BASE=$(awk '/libdi-network-bt-app\.so/ && $3=="00000000" {print $1; exit}' "/proc/$PID/maps" | cut -d- -f1)
if [ -n "$BASE" ]; then
    FUNC=$(printf '0x%x' $((0x$BASE + 0x8de0)))
    say "C1: btSendEventToUI @ $FUNC (base 0x$BASE + 0x8de0), args (8,0,20,0)"
    "$INJ" "$PID" thumb "$FUNC" 8 0 20 0 > "$OUT/10-c1-inject.txt" 2>&1
    say "    injector: $(cat "$OUT/10-c1-inject.txt")"
    i=0; while [ $i -lt 6 ]; do up7679 && break; sleep 1; i=$((i+1)); done
    if up7679; then WINNER="C1 btSendEventToUI(8,0,20,0)"; fi
else
    say "C1: SKIP -- libdi-network-bt-app.so base not found in maps."
fi

# =============================================================================
# Candidate 2 (fallback): handle_bt_app_receive_command(this,0,20,ptr).
# di-camera-app is ET_EXEC: func @ fixed 0x241b08 (ARM), this = fixed 0x005027f4
# (the CUINETFuncBluetooth singleton). ptr is any readable address (not deref'd
# on the liveview slot); we reuse the singleton address.
# =============================================================================
if [ "$WINNER" = "none" ]; then
    say "C2: handle_bt_app_receive_command @ 0x241b08, args (0x005027f4,0,20,0x005027f4)"
    "$INJ" "$PID" arm 0x241b08 0x005027f4 0 20 0x005027f4 > "$OUT/11-c2-inject.txt" 2>&1
    say "    injector: $(cat "$OUT/11-c2-inject.txt")"
    i=0; while [ $i -lt 6 ]; do up7679 && break; sleep 1; i=$((i+1)); done
    if up7679; then WINNER="C2 handle_bt_app_receive_command(...,20,...)"; fi
fi

# =============================================================================
# Candidate 0 (negative control, no ptrace): a D-Bus emit on org.bt.app_event.
# Analysis says this is DEAD (that signal carries only GATT/adapter state, and
# the subscriber drops non-state names) -- included only so the card run records
# that it does nothing. It is harmless.
# =============================================================================
if [ "$WINNER" = "none" ]; then
    say "C0: (control) dbus-send org.bt.app_event -- expected to do nothing"
    dbus-send --system --type=signal /org/bt/app_event org.bt.app_event.AppLiveview int32:20 \
        > "$OUT/12-c0-dbus.txt" 2>&1
    i=0; while [ $i -lt 4 ]; do up7679 && break; sleep 1; i=$((i+1)); done
    if up7679; then WINNER="C0 dbus-send (unexpected!)"; fi
fi

# --- proof + teardown ---------------------------------------------------------
rule
netstat -lntp > "$OUT/20-netstat-after.txt" 2>&1
say "### listening sockets AFTER:"
grep -E ':(7679|7676|80|9001)' "$OUT/20-netstat-after.txt" | tee -a "$LOG"
rule
if up7679; then
    say "RESULT: SUCCESS -- 7679 is listening. Trigger = $WINNER"
    grep ':7676' "$OUT/20-netstat-after.txt" >/dev/null 2>&1 \
        && say "        7676 (RVF streaming/UPnP) is up too." \
        || say "        (7676 not seen yet; the encoder/UPnP may lag a beat.)"
else
    say "RESULT: 7679 did NOT come up. Read 10-c1-inject.txt / 11-c2-inject.txt:"
    say "        - if the injector printed 'PTRACE_ATTACH ... EPERM', ptrace is"
    say "          blocked (SMACK/yama). See 10-rvf-trigger.md 'What remains unknown'."
    say "        - if it printed 'OK r0=...' but 7679 is still down, the call ran"
    say "          but RVF was gated (get_error_type_to_activate != 100): check"
    say "          camera mode/storage/battery, and 04/05 SMACK labels."
fi

# leave the target exactly as found; the injector already restored + detached.
rm -f "$INJ" 2>/dev/null
touch "$OUT/DONE"
say "### DONE"
