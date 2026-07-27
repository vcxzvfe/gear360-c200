#!/bin/sh
# rvf-start.sh (v3) -- RVF trigger for the SM-C200, run by dfmsd script mode.
#
# v2 established (on the bench): the loop guard works, and PROBE proved SMACK
# permits root ptrace on di-camera-app. But candidate C1 (btSendEventToUI)
# CRASHED di-camera-app -- it hijacks the main thread to synchronously re-enter
# the whole glib/ecore event-broadcast chain, which is the classic ptrace
# call-injection trap.
#
# v3 first isolates the cause, then tries a lighter call:
#   PHASE B1 -- inject libc getpid(): a pure, side-effect-free syscall wrapper.
#     If the app SURVIVES this and the injector prints "OK r0=<pid>", the
#     inject+restore mechanism itself is sound, and C1's crash was specific to
#     the heavy RVF call. If the app DIES even on getpid, the mechanism (main-
#     thread hijack) is the problem and we need a different injection strategy.
#   PHASE B2 -- only if B1 survived: inject handle_bt_app_receive_command
#     directly (F2). This skips btSendEventToUI's broadcast hand-off and runs
#     far less code in the hijacked thread; CUINETFuncDLNA::Start still async-
#     posts the heavy work to the app's own event loop.
#
# Loop guard + per-step sync as in v2. Writes only the SD card and tmpfs; no
# write to the camera's internal eMMC (mmcblk0).

OUT=/mnt/mmc/rvf-out
TG=/mnt/mmc/info.tg

# STEP 0 -- LOOP GUARD: delete our trigger before any ptrace. At most one run.
rm -f "$TG" 2>/dev/null
sync

mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: info.tg deleted (loop guard armed); v3 starting"

id > "$OUT/01-id.txt" 2>&1; sync
netstat -lntp > "$OUT/02-netstat-before.txt" 2>&1; sync
prog "STEP1: baseline captured"

PID=$(pidof di-camera-app 2>/dev/null)
[ -z "$PID" ] && PID=$(ps 2>/dev/null | awk '/di-camera-app/ && !/awk/ {print $1; exit}')
prog "STEP2: di-camera-app pid=$PID"
if [ -z "$PID" ]; then prog "FATAL: di-camera-app not running"; touch "$OUT/DONE"; sync; exit 1; fi
cat "/proc/$PID/maps" > "$OUT/03-maps.txt" 2>/dev/null; sync

echo 0 > /proc/sys/kernel/yama/ptrace_scope 2>/dev/null
TGT=$(cat "/proc/$PID/attr/current" 2>/dev/null)
[ -n "$TGT" ] && echo -n "$TGT" > /proc/self/attr/current 2>/dev/null
prog "STEP3: ptrace gating relaxed"

# stage injector into exec-capable tmpfs
INJ=""
for d in /tmp /run /dev/shm /opt/usr/tmp; do
    [ -d "$d" ] || continue
    cp /mnt/mmc/rvf-inject "$d/rvf-inject" 2>/dev/null || continue
    chmod 0755 "$d/rvf-inject" 2>/dev/null
    "$d/rvf-inject" >/dev/null 2>&1
    [ $? -eq 2 ] && { INJ="$d/rvf-inject"; break; }
    rm -f "$d/rvf-inject"
done
prog "STEP4: injector staged at ${INJ:-NONE}"
[ -z "$INJ" ] && { prog "FATAL: cannot stage injector"; touch "$OUT/DONE"; sync; exit 1; }

alive() { ps 2>/dev/null | grep -q 'di-camera-app'; }
up7679() { netstat -lntp 2>/dev/null | grep -q ':7679'; }

# --- PHASE A: read-only probe (known to pass from v2, re-confirm) ------------
"$INJ" "$PID" probe > "$OUT/06-probe.txt" 2>&1
prog "STEP5: probe rc=$? :: $(cat "$OUT/06-probe.txt")"

# =============================================================================
# PHASE B1 -- HARMLESS mechanism test: inject libc getpid().
# libc.so.6 getpid is at file offset 0x95108 (ARM). Expected: injector prints
# "OK r0=0x<pid>" (the app's own pid) and the app keeps running.
# =============================================================================
LIBC_BASE=$(awk '/\/lib\/libc\.so\.6/ && $3=="00000000" {print $1; exit}' "/proc/$PID/maps" | cut -d- -f1)
prog "STEP6: libc.so.6 base = ${LIBC_BASE:-NOT_FOUND}"
if [ -n "$LIBC_BASE" ]; then
    GP=$(printf '0x%x' $((0x$LIBC_BASE + 0x95108)))
    prog "STEP6: injecting getpid @ $GP (harmless mechanism test)"
    "$INJ" "$PID" arm "$GP" 0 0 0 0 > "$OUT/07-getpid.txt" 2>&1
    prog "STEP7: getpid injector rc=$? :: $(cat "$OUT/07-getpid.txt")"
    sleep 1
    if alive; then prog "STEP7: di-camera-app ALIVE after getpid -> inject mechanism OK"
    else prog "STEP7: di-camera-app DIED on getpid -> mechanism (main-thread hijack) is the problem"; fi
else
    prog "STEP6: SKIP getpid test (libc base not found)"
fi
sync

# =============================================================================
# PHASE B2 -- lighter RVF call: handle_bt_app_receive_command (F2), only if the
# app survived the harmless test. Fixed addresses (di-camera-app is ET_EXEC).
# =============================================================================
if alive; then
    prog "STEP8: attempting F2 handle_bt_app_receive_command(0x005027f4,0,20,0x005027f4)"
    "$INJ" "$PID" arm 0x241b08 0x005027f4 0 20 0x005027f4 > "$OUT/10-f2-inject.txt" 2>&1
    prog "STEP9: F2 injector rc=$? :: $(cat "$OUT/10-f2-inject.txt")"
    i=0; while [ $i -lt 6 ]; do up7679 && break; sleep 1; i=$((i+1)); done
    netstat -lntp > "$OUT/20-netstat-after.txt" 2>&1; sync
    if up7679; then
        prog "RESULT: SUCCESS -- 7679 is listening. RVF started with no phone."
    elif alive; then
        prog "RESULT: F2 ran, app alive, 7679 not up -> RVF gated (mode/storage/battery) or async not serviced"
    else
        prog "RESULT: F2 crashed the app -> need out-of-thread injection (LD_PRELOAD)"
    fi
else
    prog "STEP8: SKIP F2 -- app not alive after B1"
fi

rm -f "$INJ" 2>/dev/null
touch "$OUT/DONE"; sync
prog "DONE"
