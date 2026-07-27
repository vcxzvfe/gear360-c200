#!/bin/sh
# Stage-A reconnaissance for the SM-C200, run by dfmsd script mode.
#
# It is driven by info.tg -> recon.adj ("shell script /mnt/mmc/recon.sh").
# It writes ONLY to the SD card (/mnt/mmc/recon-out). It touches NO block
# device on the camera: no dd, no mount, no fw_upgrade, no write to
# /dev/mmcblk*. Every command below is read-only.
#
# Purpose: answer, from inside the running system, the questions that cannot
# be answered from outside -- which process owns which port, whether a V4L2
# capture node exists, the D-Bus surface for the RVF trigger, and whether sdbd
# offers a TCP shell -- and leave the results on the card to read on a Mac.
#
# Read tools/card/README.md before using this. The camera clock is unset, so
# output filenames are numbered, not timestamped.

OUT=/mnt/mmc/recon-out
mkdir -p "$OUT"

# Redirect all of this script's own stderr somewhere visible too.
exec 2>"$OUT/00-stderr.txt"

run() {
    # run <outfile> <label> -- everything after the second arg is the command
    _out="$OUT/$1"; _label="$2"; shift 2
    {
        echo "### $_label"
        echo "### \$ $*"
        "$@" 2>&1
        echo "### exit=$?"
    } >"$_out"
}

# --- identity and build -------------------------------------------------
run 01-id.txt          "whoami / uid"                 id
run 02-uname.txt       "kernel"                        uname -a
run 03-version.txt     "build"                         cat /etc/version.info

# --- the port-ownership question (the big one) --------------------------
# -n numeric, -l listening, -t tcp, -p show pid/program. This is what settles
# whether one process owns 80/7676/7679/9001.
run 04-netstat.txt     "listening tcp sockets + owners" netstat -lntp
run 05-ss.txt          "ss listening (cross-check)"     ss -lntp

# --- capture path -------------------------------------------------------
run 06-dev-video.txt   "V4L2 capture nodes"             ls -la /dev/video0 /dev/video1 /dev/video2 /dev/media0
run 07-dev-all.txt     "full /dev listing"              ls -la /dev

# --- process and service picture ---------------------------------------
run 08-ps.txt          "processes"                      ps
run 09-ps-ef.txt       "processes (ef, may be unsupported)" ps -ef
run 10-mount.txt       "mounts (read-only listing)"     mount
run 11-units.txt       "systemd units"                  systemctl list-units --no-pager --no-legend

# --- the RVF injection surface (read-only introspection) ----------------
# org.bt.app is the bus name libdi-network-bt-app registers against; the
# liveview event arrives here. Introspection is read-only.
run 12-dbus-btapp.txt  "introspect org.bt.app_event"    dbus-send --system --print-reply --dest=org.bt.app /org/bt/app_event org.freedesktop.DBus.Introspectable.Introspect
run 13-dbus-btsvc.txt  "introspect org.bt.app_service"  dbus-send --system --print-reply --dest=org.bt.app /org/bt/app_service org.freedesktop.DBus.Introspectable.Introspect

# --- config that decides ports and wifi mode (read-only cat) ------------
run 14-upnpcfg.txt     "UPnP config (streaming port)"   cat /mnt/mmc/.config/UPnPConfig.xml
run 15-httpcfg.txt     "http file-server config"        cat /mnt/mmc/.config/http_stream.ini
run 16-parttab.txt     "partition table (read-only)"    cat /etc/parttab
run 17-imagetab.txt    "image table (read-only)"        cat /etc/imagetab

# --- does sdbd give us a TCP shell? -------------------------------------
# Start sdbd, wait, then re-check listening sockets. If a new TCP port (often
# 26101) appears, route B1 is viable. This starts a daemon but writes no block
# device; it is undone by a power cycle.
systemctl start sdbd 2>>"$OUT/00-stderr.txt" || /usr/sbin/sdbd 2>>"$OUT/00-stderr.txt" &
sleep 3
run 18-netstat-after-sdbd.txt "listening sockets after starting sdbd" netstat -lntp

# --- finish marker ------------------------------------------------------
sync
echo "recon complete" >"$OUT/DONE"
sync
