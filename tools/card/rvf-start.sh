#!/bin/sh
# rvf-start.sh (v10) -- inject only onto futex-blocked worker threads.
#
# v9's thread map showed every thread is asleep in a syscall, and which one:
#   252 di-camera-app  poll_schedule_timeout  -- the main loop; must stay free
#   261 shell_di_app   do_msgrcv              -- what v8 crashed on
#   262 recorder       futex_wait_queue_me    }
#   264 MCB_Receiver   futex_wait_queue_me    }  the tolerant ones
#   265 MCB_Sender     futex_wait_queue_me    }
#   281 SIF Main       futex_wait_queue_me    }
#   282 SIF FileHandler futex_wait_queue_me   }
#   26x ui_th_* / DFMS do_msgrcv
#
# A hijack+restore interrupts the target thread's syscall. do_msgrcv returns
# EINTR and those threads do not retry -> the thread, and thus the whole
# process, dies. But threads in futex_wait_queue_me are inside a glibc pthread
# wait whose futex wrapper RETRIES on EINTR, so they survive the interruption.
# So v10 injects ONLY futex-blocked workers (matched by wchan, since tids shift
# per boot), never the do_msgrcv/poll ones. The freed main loop consumes the
# enqueued post and binds 7679.
#
# Per target: harmless getpid first (must keep the app alive), then
# btSendEventToUI(8,0,20,0). Checks 7679 inline, before the script-mode reboot.
# Writes only the SD card.

OUT=/mnt/mmc/rvf-out
rm -f /mnt/mmc/info.tg 2>/dev/null; sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: loop guard; v10 futex-thread injection"

id > "$OUT/01-id.txt" 2>&1
PID=$(pidof di-camera-app 2>/dev/null); [ -z "$PID" ] && PID=$(pgrep di-camera-app | head -1)
prog "STEP1: main pid=$PID"
[ -z "$PID" ] && { prog "FATAL no di-camera-app"; touch "$OUT/DONE"; sync; exit 1; }
cat /proc/$PID/maps > "$OUT/03-maps.txt" 2>/dev/null; sync

echo 0 > /proc/sys/kernel/yama/ptrace_scope 2>/dev/null
TGT=$(cat /proc/$PID/attr/current 2>/dev/null); [ -n "$TGT" ] && echo -n "$TGT" > /proc/self/attr/current 2>/dev/null

INJ=""
for d in /tmp /run /dev/shm /opt/usr/tmp; do
    [ -d "$d" ] || continue
    cp /mnt/mmc/rvf-inject "$d/rvf-inject" 2>/dev/null || continue
    chmod 0755 "$d/rvf-inject" 2>/dev/null
    "$d/rvf-inject" >/dev/null 2>&1; [ $? -eq 2 ] && { INJ="$d/rvf-inject"; break; }
    rm -f "$d/rvf-inject"
done
prog "STEP2: injector at ${INJ:-NONE}"
[ -z "$INJ" ] && { prog "FATAL no injector"; touch "$OUT/DONE"; sync; exit 1; }

alive() { ps 2>/dev/null | grep -q di-camera-app; }
up7679() { netstat -lntp 2>/dev/null | grep -q ':7679'; }

LIBC_BASE=$(awk '$6 ~ /\/libc-[0-9]/ && $2=="r-xp"{split($1,a,"-");print a[1];exit}' /proc/$PID/maps)
BT_BASE=$(awk '/libdi-network-bt-app\.so/ && $2=="r-xp"{split($1,a,"-");print a[1];exit}' /proc/$PID/maps)
[ -z "$BT_BASE" ] && BT_BASE=$(awk '/libdi-network-bt-app\.so/ && $3=="00000000"{split($1,a,"-");print a[1];exit}' /proc/$PID/maps)
prog "STEP3: libc=$LIBC_BASE bt-app=$BT_BASE"

# select worker threads blocked in futex (tolerant of EINTR), by wchan
FUTEX_TIDS=""
for T in $(ls /proc/$PID/task/ 2>/dev/null | grep -v "^$PID\$"); do
    W=$(cat /proc/$PID/task/$T/wchan 2>/dev/null)
    case "$W" in *futex*) FUTEX_TIDS="$FUTEX_TIDS $T";; esac
done
prog "STEP4: futex-blocked workers =${FUTEX_TIDS:- none}"
[ -z "$FUTEX_TIDS" ] && { prog "FATAL no futex-blocked worker"; touch "$OUT/DONE"; sync; exit 1; }

for WT in $FUTEX_TIDS; do
    COMM=$(cat /proc/$PID/task/$WT/comm 2>/dev/null)
    prog "--- worker $WT ($COMM) ---"
    if [ -n "$LIBC_BASE" ]; then
        GP=$(printf '0x%x' $((0x$LIBC_BASE + 0x95108)))
        "$INJ" "$WT" arm "$GP" 0 0 0 0 > "$OUT/10-w$WT-getpid.txt" 2>&1
        prog "  getpid rc=$? :: $(cat "$OUT/10-w$WT-getpid.txt")"
        if ! alive; then prog "  app DIED on getpid@$WT -> not tolerant; stop"; break; fi
        prog "  app ALIVE after getpid@$WT (futex thread tolerated the hijack)"
    fi
    if [ -n "$BT_BASE" ]; then
        FUNC=$(printf '0x%x' $((0x$BT_BASE + 0x8de0)))
        "$INJ" "$WT" thumb "$FUNC" 8 0 20 0 > "$OUT/11-w$WT-trigger.txt" 2>&1
        prog "  btSendEventToUI rc=$? :: $(cat "$OUT/11-w$WT-trigger.txt")"
    fi
    i=0; while [ $i -lt 6 ]; do up7679 && break; sleep 1; i=$((i+1)); done
    if up7679; then
        prog "RESULT: *** SUCCESS 7679 LISTENING via $WT ($COMM) -- RVF, no phone ***"
        break
    fi
    alive && prog "  $WT: trigger ran, app alive, 7679 not up; next futex worker" \
          || { prog "  $WT: app died after trigger; stop"; break; }
done

netstat -lntp > "$OUT/20-netstat-after.txt" 2>&1; sync
up7679 && prog "FINAL: 7679 UP" || prog "FINAL: 7679 not up"
rm -f "$INJ" 2>/dev/null
touch "$OUT/DONE"; sync
prog "DONE"
