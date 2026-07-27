#!/bin/sh
# rvf-start.sh (v6) -- LD_PRELOAD RVF trigger for the SM-C200 (systemd 208).
#
# v5 failed to restart: systemd-run 208 has no --collect, so the restart was
# never launched and rvftrig.so never loaded. v6:
#   * uses systemd-run options that systemd 208 actually has (--scope --unit),
#     with a setsid fallback, and --no-block so the request reaches the manager
#     even if our cgroup is about to be killed by the restart;
#   * BEFORE restarting, records whether the LD_PRELOAD drop-in actually took
#     effect (systemctl show ... Environment / DropInPaths) and what the
#     service's EnvironmentFile contains -- so if the .so still doesn't load we
#     know whether the drop-in was the problem.
#
# Writes only SD card / tmpfs(/run) / ext4(/opt/usr). No camera-eMMC write.

OUT=/mnt/mmc/rvf-out
TG=/mnt/mmc/info.tg
SO_SRC=/mnt/mmc/rvftrig.so
SO_DST=/opt/usr/rvftrig.so
DROPDIR=/run/systemd/system/di-camera-app.service.d
DROPIN=$DROPDIR/rvf-preload.conf

rm -f "$TG" 2>/dev/null            # loop guard
sync
mkdir -p "$OUT"
exec 2>"$OUT/00-stderr.txt"
prog() { echo "$@" >> "$OUT/00-progress.txt"; sync; }
prog "STEP0: info.tg deleted (loop guard); v6 LD_PRELOAD (systemd 208)"

id > "$OUT/01-id.txt" 2>&1; sync
OLDPID=$(pidof di-camera-app 2>/dev/null); [ -z "$OLDPID" ] && OLDPID=$(pgrep di-camera-app 2>/dev/null | head -1)
prog "STEP1: di-camera-app old pid=$OLDPID"

# 1. place .so
if ! cp "$SO_SRC" "$SO_DST" 2>>"$OUT/00-stderr.txt"; then
    prog "FATAL: cp rvftrig.so -> $SO_DST failed"; touch "$OUT/DONE"; sync; exit 1
fi
chmod 0755 "$SO_DST" 2>/dev/null
prog "STEP2: rvftrig.so -> $SO_DST"

# 2. drop-in adding LD_PRELOAD
mkdir -p "$DROPDIR"
printf '[Service]\nEnvironment=LD_PRELOAD=%s\n' "$SO_DST" > "$DROPIN"
sync
prog "STEP3: drop-in written"

# 3. daemon-reload, then VERIFY the drop-in took effect
systemctl daemon-reload 2>>"$OUT/00-stderr.txt"
prog "STEP4: daemon-reload done"
systemctl show di-camera-app -p Environment -p DropInPaths -p FragmentPath \
    > "$OUT/04-unit-env.txt" 2>&1; sync
cat /run/tizen-mobile-env > "$OUT/05-envfile.txt" 2>&1; sync
if grep -q "LD_PRELOAD=$SO_DST" "$OUT/04-unit-env.txt"; then
    prog "STEP5: VERIFIED drop-in in effect (LD_PRELOAD present in unit Environment)"
else
    prog "STEP5: WARNING -- LD_PRELOAD NOT visible in unit Environment; see 04-unit-env.txt"
fi

# 4. restart, from outside our cgroup, non-blocking
prog "STEP6: restarting di-camera-app (systemd-run --scope, then fallbacks)"
sync
if systemd-run --scope --unit=rvf-restart /usr/bin/systemctl --no-block restart di-camera-app \
        >> "$OUT/06-restart.txt" 2>&1; then
    prog "STEP7: systemd-run --scope returned ok"
else
    prog "STEP7: systemd-run --scope failed (rc=$?); trying setsid + --no-block"
    setsid /usr/bin/systemctl --no-block restart di-camera-app >> "$OUT/06-restart.txt" 2>&1 &
    sleep 2
    prog "STEP7b: setsid restart dispatched"
fi

prog "STEP8: restart requested. New di-camera-app should load rvftrig.so;"
prog "       it writes rvf-out/50-preload.txt with the trigger + 7679 result."
touch "$OUT/DONE"; sync
prog "DONE (script side)"
