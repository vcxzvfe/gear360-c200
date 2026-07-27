#!/bin/sh
# rvf-start.sh (v7) -- LD_PRELOAD RVF trigger for the SM-C200, kill-based restart.
#
# v6 confirmed the LD_PRELOAD drop-in TAKES EFFECT (systemctl show reported
# Environment=LD_PRELOAD=...), but the restart failed: in the dfmsd script
# context, systemd-run/systemctl restart cannot reach the systemd bus
# ("Failed to create new bus connection"). daemon-reload, however, works.
#
# v7 avoids the bus entirely: the drop-in also sets Restart=always, and we
# trigger the reload by KILLing di-camera-app (a plain signal, no bus). systemd
# then restarts it with the LD_PRELOAD drop-in already in effect. The .so
# self-deletes on load, so at most one trigger happens even with Restart=always.
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
prog "STEP0: info.tg deleted (loop guard); v7 kill-based LD_PRELOAD"

id > "$OUT/01-id.txt" 2>&1; sync
OLDPID=$(pidof di-camera-app 2>/dev/null); [ -z "$OLDPID" ] && OLDPID=$(pgrep di-camera-app 2>/dev/null | head -1)
prog "STEP1: di-camera-app old pid=$OLDPID"
if [ -z "$OLDPID" ]; then prog "FATAL: di-camera-app not running"; touch "$OUT/DONE"; sync; exit 1; fi

# 1. place .so
if ! cp "$SO_SRC" "$SO_DST" 2>>"$OUT/00-stderr.txt"; then
    prog "FATAL: cp rvftrig.so -> $SO_DST failed"; touch "$OUT/DONE"; sync; exit 1
fi
chmod 0755 "$SO_DST" 2>/dev/null
prog "STEP2: rvftrig.so -> $SO_DST"

# 2. drop-in: LD_PRELOAD + Restart=always so a kill reloads the app with us
mkdir -p "$DROPDIR"
printf '[Service]\nEnvironment=LD_PRELOAD=%s\nRestart=always\nRestartSec=1\n' "$SO_DST" > "$DROPIN"
sync
prog "STEP3: drop-in written (LD_PRELOAD + Restart=always)"

# 3. daemon-reload (this works even though restart does not) + verify
systemctl daemon-reload 2>>"$OUT/00-stderr.txt"
prog "STEP4: daemon-reload done"
systemctl show di-camera-app -p Environment -p Restart -p DropInPaths \
    > "$OUT/04-unit-env.txt" 2>&1; sync
if grep -q "LD_PRELOAD=$SO_DST" "$OUT/04-unit-env.txt"; then
    prog "STEP5: VERIFIED LD_PRELOAD + $(grep -o 'Restart=[a-z]*' "$OUT/04-unit-env.txt" | head -1) in effect"
else
    prog "STEP5: WARNING LD_PRELOAD not visible; see 04-unit-env.txt"
fi

# 4. protect diagnostics, then KILL to trigger Restart=always (no bus needed)
touch "$OUT/DONE"; sync
prog "STEP6: killing di-camera-app pid=$OLDPID (SIGTERM) to trigger reload"
sync
kill "$OLDPID" 2>>"$OUT/00-stderr.txt"
# escalate if it ignores SIGTERM; we may be cgroup-killed ourselves here.
sleep 4
if kill -0 "$OLDPID" 2>/dev/null; then
    prog "STEP7: still alive after SIGTERM; sending SIGKILL"
    kill -9 "$OLDPID" 2>>"$OUT/00-stderr.txt"
fi
prog "STEP8: kill sent. systemd should restart di-camera-app WITH rvftrig.so."
prog "       The .so writes rvf-out/50-preload.txt with the trigger + 7679 result."
sync
prog "DONE (script side)"
