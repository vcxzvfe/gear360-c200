#!/bin/sh
# rvf-start.sh (v5) -- LD_PRELOAD RVF trigger for the SM-C200, via dfmsd.
#
# ptrace call-injection was proven unworkable (v1-v4, 11-injection-bench-log.md):
# hijacking di-camera-app's main thread crashes it, even for getpid. v5 instead
# makes the app load rvftrig.so via LD_PRELOAD at a service RESTART, so the
# trigger runs inside the fully-initialised app on its OWN thread -- the phone's
# real context. No ptrace.
#
# Mechanism (all writes are to tmpfs /run, ext4 /opt/usr, and the SD card --
# never the camera's internal-firmware eMMC partitions on mmcblk0):
#   1. copy rvftrig.so to /opt/usr (ext4 rw, exec-capable)
#   2. systemd drop-in in /run (tmpfs) adds Environment=LD_PRELOAD=...
#   3. systemd-run launches the restart from OUTSIDE dfmsd's cgroup, so it
#      survives di-camera-app being killed (which would otherwise kill us)
#   4. the new di-camera-app loads rvftrig.so; its thread waits, calls
#      btSendEventToUI(8,0,20,0), and logs to /mnt/mmc/rvf-out/50-preload.txt
#      including whether 7679 came up.
#
# After running: wait ~60s from power-on, then power off and read
# rvf-out/50-preload.txt.

OUT=/mnt/mmc/rvf-out
TG=/mnt/mmc/info.tg
SO_SRC=/mnt/mmc/rvftrig.so
SO_DST=/opt/usr/rvftrig.so
DROPDIR=/run/systemd/system/di-camera-app.service.d
DROPIN=$DROPDIR/rvf-preload.conf

rm -f "$TG" 2>/dev/null            # loop guard: at most one run
sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: info.tg deleted (loop guard); v5 LD_PRELOAD approach"

id > "$OUT/01-id.txt" 2>&1; sync
OLDPID=$(pidof di-camera-app 2>/dev/null)
prog "STEP1: di-camera-app old pid=$OLDPID"

# --- 1. place the .so where it can be exec'd/loaded --------------------------
if ! cp "$SO_SRC" "$SO_DST" 2>>"$OUT/00-stderr.txt"; then
    prog "FATAL: could not copy rvftrig.so to $SO_DST (is it on the card?)"
    touch "$OUT/DONE"; sync; exit 1
fi
chmod 0755 "$SO_DST" 2>/dev/null
prog "STEP2: rvftrig.so -> $SO_DST ($(stat -c %s "$SO_DST" 2>/dev/null || echo '?') bytes)"

# --- 2. systemd drop-in adding LD_PRELOAD (tmpfs, no rootfs write) -----------
mkdir -p "$DROPDIR"
{
    echo "[Service]"
    echo "Environment=LD_PRELOAD=$SO_DST"
} > "$DROPIN"
sync
prog "STEP3: drop-in written: $DROPIN"
cat "$DROPIN" >> "$OUT/02-dropin.txt" 2>/dev/null; sync

# reset our own env so we don't get preloaded into helper processes
systemctl daemon-reload 2>>"$OUT/00-stderr.txt"
prog "STEP4: daemon-reload done"

# --- 3. restart di-camera-app from OUTSIDE our cgroup ------------------------
# systemd-run hands the restart to the systemd manager in its own transient
# unit, so it completes even though restarting di-camera-app kills dfmsd (us).
prog "STEP5: launching restart via systemd-run (we may be killed here; that's expected)"
sync
systemd-run --collect --unit=rvf-restart /usr/bin/systemctl restart di-camera-app \
    >> "$OUT/03-systemd-run.txt" 2>&1
RC=$?
prog "STEP6: systemd-run rc=$RC (if we got here, dfmsd survived the restart)"

# Fallback if systemd-run is unavailable/failed: detach a restart and exit.
if [ "$RC" -ne 0 ]; then
    prog "STEP6: systemd-run failed; trying setsid detached restart"
    setsid sh -c 'sleep 1; /usr/bin/systemctl restart di-camera-app' \
        >> "$OUT/03-systemd-run.txt" 2>&1 &
fi

prog "STEP7: restart requested. The new di-camera-app should LD_PRELOAD rvftrig.so."
prog "       Watch rvf-out/50-preload.txt for the trigger + 7679 result."
touch "$OUT/DONE"; sync
prog "DONE (script side; the .so writes 50-preload.txt after restart)"
