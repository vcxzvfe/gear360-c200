#!/bin/sh
# rvf-start.sh (v9) -- worker-thread RECON only, no injection.
#
# v8+__WALL finally attached a worker (261) for real -- and injecting getpid
# there crashed the app too. Lesson: a hijack+restore corrupts whatever syscall
# the target thread was blocked in, and a fatal signal in ANY thread kills the
# whole process. So the only safe injection target is a thread that is NOT
# blocked in a syscall at the moment we attach (state R = running), or a thread
# whose disruption the app tolerates.
#
# Rather than keep crashing one worker per boot, this run only INSPECTS every
# thread: name (comm), scheduler state, and what it is waiting on (wchan/stack).
# No ptrace, no injection -- it cannot crash. The output picks the right target
# for the next run.
#
# Writes only the SD card.

OUT=/mnt/mmc/rvf-out
rm -f /mnt/mmc/info.tg 2>/dev/null; sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: loop guard; v9 THREAD RECON (no injection)"

id > "$OUT/01-id.txt" 2>&1
PID=$(pidof di-camera-app 2>/dev/null); [ -z "$PID" ] && PID=$(pgrep di-camera-app|head -1)
prog "STEP1: di-camera-app main pid=$PID"
[ -z "$PID" ] && { prog "FATAL no di-camera-app"; touch "$OUT/DONE"; sync; exit 1; }

# Per-thread report. For each tid under /proc/PID/task:
#   comm   = thread name
#   state  = R(running) S(sleep) D(uninterruptible) etc. -- from field 3 of stat
#   wchan  = kernel function it is blocked in (a syscall name, or 0 if running)
#   stack  = kernel stack (top frames) if readable
REP="$OUT/30-threads.txt"
: > "$REP"
for T in $PID $(ls /proc/$PID/task/ 2>/dev/null | grep -v "^$PID\$"); do
    COMM=$(cat /proc/$PID/task/$T/comm 2>/dev/null)
    STATE=$(awk '{print $3}' /proc/$PID/task/$T/stat 2>/dev/null)
    WCHAN=$(cat /proc/$PID/task/$T/wchan 2>/dev/null)
    {
        echo "=== tid $T  comm=$COMM  state=$STATE  wchan=$WCHAN $([ "$T" = "$PID" ] && echo '(MAIN)')"
        echo "  --- kernel stack (top) ---"
        head -8 /proc/$PID/task/$T/stack 2>/dev/null | sed 's/^/    /'
    } >> "$REP"
    sync
done
prog "STEP2: wrote per-thread comm/state/wchan/stack for $(ls /proc/$PID/task/ | wc -l) threads"

# A compact summary line per thread, easy to scan.
SUM="$OUT/31-summary.txt"
{
    printf '%-6s %-16s %-3s %s\n' TID COMM ST WCHAN
    for T in $PID $(ls /proc/$PID/task/ 2>/dev/null | grep -v "^$PID\$"); do
        printf '%-6s %-16s %-3s %s%s\n' \
            "$T" \
            "$(cat /proc/$PID/task/$T/comm 2>/dev/null)" \
            "$(awk '{print $3}' /proc/$PID/task/$T/stat 2>/dev/null)" \
            "$(cat /proc/$PID/task/$T/wchan 2>/dev/null)" \
            "$([ "$T" = "$PID" ] && echo ' (MAIN)')"
    done
} > "$SUM" 2>&1
sync
prog "STEP3: summary written to 31-summary.txt"

# Also: which threads are in state R (running) right now -- best inject targets.
RUN=$(for T in $(ls /proc/$PID/task/ 2>/dev/null); do
        S=$(awk '{print $3}' /proc/$PID/task/$T/stat 2>/dev/null)
        [ "$S" = "R" ] && echo "$T"
      done | tr '\n' ' ')
prog "STEP4: threads currently in state R (running) = ${RUN:-none}"

touch "$OUT/DONE"; sync
prog "DONE (recon only; nothing injected, app untouched)"
