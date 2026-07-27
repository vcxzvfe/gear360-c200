#!/bin/sh
# rvf-start.sh (v2) -- RVF trigger for the SM-C200, run by dfmsd script mode.
#
# v2 fixes two failures seen on the bench in v1:
#   (1) A crash boot-loop. If a later step crashes di-camera-app and info.tg is
#       still on the card, the camera reboots and re-runs this script forever.
#       FIX: STEP 0 deletes our own info.tg trigger BEFORE anything risky, so
#       this script runs at most once regardless of what happens after.
#   (2) Lost diagnostics. exfat writes were never flushed before the crash, so
#       the card came back with no rvf-out at all.
#       FIX: a progress file is sync'd after every phase, and the risky ptrace
#       work is gated behind a read-only probe.
#
# It writes ONLY to the SD card and to tmpfs (RAM). Deleting info.tg on the SD
# card is a write to the SD card (mmcblk1, exfat), NOT to the camera's internal
# eMMC (mmcblk0) -- the safety line ("no block write to the camera") holds.
#
# Trigger value is proven: command id 20 = EXE_LIVEVIEW starts RVF (10-rvf-trigger.md).

OUT=/mnt/mmc/rvf-out
TG=/mnt/mmc/info.tg

# ============================================================================
# STEP 0 -- LOOP GUARD. Delete our own trigger first, before any ptrace. Even if
# a later step crashes di-camera-app and the camera reboots, info.tg is gone, so
# the script does not re-run. At most one execution, ever.
# ============================================================================
rm -f "$TG" 2>/dev/null
sync

mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: info.tg deleted (loop guard armed); starting"

# --- baseline, each sync'd so a later crash still leaves the trail -----------
id > "$OUT/01-id.txt" 2>&1; sync
netstat -lntp > "$OUT/02-netstat-before.txt" 2>&1; sync
grep -q ':7679' "$OUT/02-netstat-before.txt" && prog "NOTE: 7679 already up before we started"
prog "STEP1: baseline captured"

PID=$(pidof di-camera-app 2>/dev/null)
[ -z "$PID" ] && PID=$(ps 2>/dev/null | awk '/di-camera-app/ && !/awk/ {print $1; exit}')
prog "STEP2: di-camera-app pid=$PID"
if [ -z "$PID" ]; then
    prog "FATAL: di-camera-app not running"
    touch "$OUT/DONE"; sync; exit 1
fi
cp "/proc/$PID/maps" "$OUT/03-maps.txt" 2>/dev/null; sync
cat "/proc/$PID/attr/current" > "$OUT/04-target-smack.txt" 2>/dev/null; sync

# best-effort relax ptrace gating (root usually enough; Tizen SMACK may not be)
echo 0 > /proc/sys/kernel/yama/ptrace_scope 2>/dev/null
TGT=$(cat "/proc/$PID/attr/current" 2>/dev/null)
[ -n "$TGT" ] && echo -n "$TGT" > /proc/self/attr/current 2>/dev/null
cat /proc/self/attr/current > "$OUT/05-our-smack.txt" 2>/dev/null; sync
prog "STEP3: ptrace gating relaxed (yama=0, smack matched best-effort)"

# --- stage injector into exec-capable tmpfs (card is likely noexec) ----------
INJ=""
for d in /tmp /run /dev/shm /opt/usr/tmp; do
    [ -d "$d" ] || continue
    cp /mnt/mmc/rvf-inject "$d/rvf-inject" 2>/dev/null || continue
    chmod 0755 "$d/rvf-inject" 2>/dev/null
    "$d/rvf-inject" >/dev/null 2>&1        # no args -> usage, exit 2 => execable
    [ $? -eq 2 ] && { INJ="$d/rvf-inject"; break; }
    rm -f "$d/rvf-inject"
done
prog "STEP4: injector staged at ${INJ:-NONE}"
if [ -z "$INJ" ]; then
    prog "FATAL: could not stage injector (card noexec everywhere?)"
    touch "$OUT/DONE"; sync; exit 1
fi

# ============================================================================
# PHASE A -- read-only ptrace PROBE. Attach and detach only, no register writes,
# no call. This answers "does SMACK permit ptrace?" WITHOUT any crash risk. If
# this fails, we stop here having changed nothing in the target.
# ============================================================================
"$INJ" "$PID" probe > "$OUT/06-probe.txt" 2>&1
PROBE_RC=$?
prog "STEP5: probe rc=$PROBE_RC :: $(cat "$OUT/06-probe.txt")"
if [ "$PROBE_RC" -ne 0 ]; then
    prog "STOP: ptrace attach is BLOCKED (SMACK/yama). No injection attempted."
    prog "      Next: UART route, or LD_PRELOAD-at-launch. See 10-rvf-trigger.md."
    touch "$OUT/DONE"; sync
    exit 0
fi

# ============================================================================
# PHASE B -- injection. Only reached when the probe proved ptrace works. info.tg
# is already gone, so a crash here cannot loop. We try ONLY candidate C1 this
# run (btSendEventToUI), to isolate one variable; C2 is a separate later run.
# ============================================================================
prog "STEP6: probe OK -> attempting C1 btSendEventToUI(8,0,20,0)"
BASE=$(awk '/libdi-network-bt-app\.so/ && $3=="00000000" {print $1; exit}' "/proc/$PID/maps" | cut -d- -f1)
if [ -z "$BASE" ]; then
    prog "STEP6: SKIP C1 -- libdi-network-bt-app base not in maps"
else
    FUNC=$(printf '0x%x' $((0x$BASE + 0x8de0)))
    prog "STEP6: C1 func=$FUNC (base 0x$BASE + 0x8de0)"
    "$INJ" "$PID" thumb "$FUNC" 8 0 20 0 > "$OUT/10-c1-inject.txt" 2>&1
    prog "STEP7: C1 injector rc=$? :: $(cat "$OUT/10-c1-inject.txt")"
fi
sync

# --- give the async RVF start a few seconds, then prove it -------------------
i=0; while [ $i -lt 6 ]; do netstat -lntp 2>/dev/null | grep -q ':7679' && break; sleep 1; i=$((i+1)); done
netstat -lntp > "$OUT/20-netstat-after.txt" 2>&1; sync
if grep -q ':7679' "$OUT/20-netstat-after.txt"; then
    prog "RESULT: SUCCESS -- 7679 is listening. RVF started with no phone."
else
    prog "RESULT: injection ran, 7679 not up. Either app crashed (check that it"
    prog "        is still alive: 21-ps-after.txt) or RVF was gated (mode/batt)."
fi
ps > "$OUT/21-ps-after.txt" 2>&1; sync
grep -q 'di-camera-app' "$OUT/21-ps-after.txt" && prog "di-camera-app still alive after inject" || prog "di-camera-app GONE after inject (the call crashed it)"

rm -f "$INJ" 2>/dev/null
touch "$OUT/DONE"; sync
prog "DONE"
