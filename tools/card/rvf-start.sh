#!/bin/sh
# rvf-start.sh (v4) -- mechanism-isolation run for the SM-C200.
#
# Bench history:
#   v2: loop guard OK; PROBE proved SMACK permits root ptrace. Candidate C1
#       (btSendEventToUI, main-thread hijack) crashed di-camera-app.
#   v3: candidate F2 (handle_bt_app_receive_command) ALSO crashed it. Two
#       different call sites crashing => the problem is hijacking the main
#       thread to run the RVF chain synchronously, not any one function. Also,
#       the getpid mechanism test was skipped because the libc match was wrong
#       (device libc is /lib/libc-2.13.so, not libc.so.6).
#
# v4 does ONE thing: inject libc getpid() -- a pure, side-effect-free call --
# and report whether di-camera-app survives. NO RVF injection this run, so it
# cannot crash. The result decides the next strategy:
#   * app SURVIVES getpid  -> the inject+restore machinery is sound; the RVF
#     crashes are purely about running that chain in the hijacked main thread.
#     Next: run the trigger from a NON-main thread (inject a dlopen of a tiny
#     .so that spawns its own thread -- the phone's real call context).
#   * app DIES on getpid    -> main-thread hijack is itself unsafe on this app;
#     even a dlopen injection would crash. Next: LD_PRELOAD at service restart,
#     no ptrace at all.
#
# Loop guard + per-step sync. Writes only the SD card and tmpfs.

OUT=/mnt/mmc/rvf-out
TG=/mnt/mmc/info.tg

rm -f "$TG" 2>/dev/null        # STEP 0 loop guard: at most one run
sync

mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: info.tg deleted (loop guard); v4 (getpid mechanism test only)"

id > "$OUT/01-id.txt" 2>&1; sync
PID=$(pidof di-camera-app 2>/dev/null)
[ -z "$PID" ] && PID=$(ps 2>/dev/null | awk '/di-camera-app/ && !/awk/ {print $1; exit}')
prog "STEP1: di-camera-app pid=$PID"
[ -z "$PID" ] && { prog "FATAL: di-camera-app not running"; touch "$OUT/DONE"; sync; exit 1; }
cat "/proc/$PID/maps" > "$OUT/03-maps.txt" 2>/dev/null; sync

echo 0 > /proc/sys/kernel/yama/ptrace_scope 2>/dev/null
TGT=$(cat "/proc/$PID/attr/current" 2>/dev/null)
[ -n "$TGT" ] && echo -n "$TGT" > /proc/self/attr/current 2>/dev/null
prog "STEP2: ptrace gating relaxed"

INJ=""
for d in /tmp /run /dev/shm /opt/usr/tmp; do
    [ -d "$d" ] || continue
    cp /mnt/mmc/rvf-inject "$d/rvf-inject" 2>/dev/null || continue
    chmod 0755 "$d/rvf-inject" 2>/dev/null
    "$d/rvf-inject" >/dev/null 2>&1
    [ $? -eq 2 ] && { INJ="$d/rvf-inject"; break; }
    rm -f "$d/rvf-inject"
done
prog "STEP3: injector staged at ${INJ:-NONE}"
[ -z "$INJ" ] && { prog "FATAL: cannot stage injector"; touch "$OUT/DONE"; sync; exit 1; }

alive() { ps 2>/dev/null | grep -q 'di-camera-app'; }

# read-only probe (re-confirm)
"$INJ" "$PID" probe > "$OUT/06-probe.txt" 2>&1
prog "STEP4: probe rc=$? :: $(cat "$OUT/06-probe.txt")"

# ---- the one experiment: harmless getpid() injection --------------------
# Device libc is /lib/libc-2.13.so; getpid is at file offset 0x95108 (ARM).
# Match the r-xp (code) segment of any /lib/libc-<version>.so.
LIBC_BASE=$(awk '$6 ~ /\/libc-[0-9]/ && $2=="r-xp" {split($1,a,"-"); print a[1]; exit}' "/proc/$PID/maps")
prog "STEP5: libc base = ${LIBC_BASE:-NOT_FOUND}"
if [ -z "$LIBC_BASE" ]; then
    prog "FATAL: libc base not found; dumping libc maps lines to 08-libc-maps.txt"
    grep -i libc "/proc/$PID/maps" > "$OUT/08-libc-maps.txt" 2>&1; sync
    touch "$OUT/DONE"; sync; exit 1
fi
GP=$(printf '0x%x' $((0x$LIBC_BASE + 0x95108)))
prog "STEP6: injecting getpid @ $GP  (expect OK r0=$(printf '0x%x' "$PID"))"
"$INJ" "$PID" arm "$GP" 0 0 0 0 > "$OUT/07-getpid.txt" 2>&1
prog "STEP7: getpid injector rc=$? :: $(cat "$OUT/07-getpid.txt")"
sleep 1
if alive; then
    prog "RESULT: di-camera-app ALIVE after getpid -> inject mechanism is SOUND."
    prog "        Next strategy: non-main-thread call (dlopen a .so that spawns a thread)."
else
    prog "RESULT: di-camera-app DIED on getpid -> main-thread hijack is unsafe on this app."
    prog "        Next strategy: LD_PRELOAD at service restart (no ptrace)."
fi

rm -f "$INJ" 2>/dev/null
touch "$OUT/DONE"; sync
prog "DONE"
