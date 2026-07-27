#!/bin/sh
# rvf-start.sh (v8) -- inject onto a NON-MAIN thread.
#
# Key insight from the vconf teardown: btSendEventToUI/handle_bt_app_receive_command
# only ENQUEUE a post; the app's OWN main event loop later runs
# process_start -> process_common_activate -> StartRVFDevice, which binds 7679.
# v1-v7 all injected onto the MAIN thread (pid == tid), which is exactly the
# thread that must stay free to service that post -- hijacking it stalled the
# loop and corrupted its syscall, crashing the app even for getpid.
#
# v8 attaches a WORKER thread instead (a tid != main pid). The worker enqueues
# the post; the untouched main loop consumes it and binds 7679. First a harmless
# getpid on the worker confirms the app survives a worker hijack; only then the
# real btSendEventToUI(8,0,20,0).
#
# Must finish before dfmsd reboots the camera at script-mode exit, so it checks
# 7679 right here. Writes only the SD card. No block-device write.

OUT=/mnt/mmc/rvf-out
TG=/mnt/mmc/info.tg
rm -f "$TG" 2>/dev/null; sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: loop guard; v8 worker-thread injection"

id > "$OUT/01-id.txt" 2>&1; sync
PID=$(pidof di-camera-app 2>/dev/null); [ -z "$PID" ] && PID=$(pgrep di-camera-app|head -1)
prog "STEP1: di-camera-app main pid=$PID"
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

# enumerate worker threads (tid != main pid)
WORKERS=$(ls /proc/$PID/task/ 2>/dev/null | grep -v "^$PID\$")
echo "$WORKERS" > "$OUT/04-workers.txt"; sync
prog "STEP3: worker tids = $(echo $WORKERS | tr '\n' ' ')"
[ -z "$WORKERS" ] && { prog "FATAL no worker threads"; touch "$OUT/DONE"; sync; exit 1; }

LIBC_BASE=$(awk '$6 ~ /\/libc-[0-9]/ && $2=="r-xp"{split($1,a,"-");print a[1];exit}' /proc/$PID/maps)
BT_BASE=$(awk '/libdi-network-bt-app\.so/ && $2=="r-xp"{split($1,a,"-");print a[1];exit}' /proc/$PID/maps)
[ -z "$BT_BASE" ] && BT_BASE=$(awk '/libdi-network-bt-app\.so/ && $3=="00000000"{split($1,a,"-");print a[1];exit}' /proc/$PID/maps)
prog "STEP4: libc=$LIBC_BASE bt-app=$BT_BASE"

# try each worker: harmless getpid first (must keep app alive), then trigger.
N=0
for WT in $WORKERS; do
    N=$((N+1)); [ $N -gt 4 ] && { prog "STEP: tried 4 workers, stopping"; break; }
    prog "--- worker $WT ---"
    if [ -n "$LIBC_BASE" ]; then
        GP=$(printf '0x%x' $((0x$LIBC_BASE + 0x95108)))
        "$INJ" "$WT" arm "$GP" 0 0 0 0 > "$OUT/10-w$WT-getpid.txt" 2>&1
        prog "  getpid on $WT: rc=$? :: $(cat "$OUT/10-w$WT-getpid.txt")"
        if ! alive; then prog "  app DIED hijacking worker $WT (getpid) -> skip"; continue; fi
        prog "  app alive after getpid on worker $WT (main loop untouched)"
    fi
    if [ -n "$BT_BASE" ]; then
        FUNC=$(printf '0x%x' $((0x$BT_BASE + 0x8de0)))
        "$INJ" "$WT" thumb "$FUNC" 8 0 20 0 > "$OUT/11-w$WT-trigger.txt" 2>&1
        prog "  btSendEventToUI on $WT: rc=$? :: $(cat "$OUT/11-w$WT-trigger.txt")"
    fi
    i=0; while [ $i -lt 6 ]; do up7679 && break; sleep 1; i=$((i+1)); done
    if up7679; then
        prog "RESULT: *** SUCCESS 7679 LISTENING via worker $WT -- RVF, no phone ***"
        netstat -lntp > "$OUT/20-netstat-after.txt" 2>&1; sync
        break
    fi
    alive && prog "  worker $WT: trigger ran, app alive, 7679 not up yet" || prog "  worker $WT: app died"
    alive || break
done

netstat -lntp > "$OUT/20-netstat-after.txt" 2>&1; sync
up7679 && prog "FINAL: 7679 UP" || prog "FINAL: 7679 not up"
rm -f "$INJ" 2>/dev/null
touch "$OUT/DONE"; sync
prog "DONE"
