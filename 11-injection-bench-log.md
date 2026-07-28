# RVF-trigger bench log — SM-C200 (AQK1 unit)

Chronological record of what was tried on real hardware to start Remote View
Finder from a root shell, and what each attempt proved. Raw outputs are archived
under `research/rvf-out-*`.

The command value is settled: **id 20 = `EXE_LIVEVIEW`** (two-binary objdump
cross-check, `10-rvf-trigger.md`). Everything below is about *delivery* — how to
make the running `di-camera-app` execute the call.

| Run | What it did | Result | What it proved |
|---|---|---|---|
| v1 | ptrace-inject `btSendEventToUI(8,0,20,0)` (main thread), no loop guard | **boot loop** | A crash + a live `info.tg` = infinite reboot. Also: exfat writes lost on crash → no diagnostics. |
| v2 | + loop guard (delete `info.tg` first), + probe, per-step sync | probe **OK**; C1 crashed app once, no loop | `[VERIFIED]` SMACK permits root ptrace. C1 (`btSendEventToUI`) crashes the app. |
| v3 | try F2 `handle_bt_app_receive_command` instead | F2 **also crashed**; getpid test skipped (libc match bug) | Two different call sites crash ⇒ not a per-function issue. |
| v4 | inject harmless `getpid()` only (fixed libc match) | **getpid crashed the app too** | `[VERIFIED]` The problem is main-thread hijack *itself*, not the RVF chain. |

## The finding that redirects the project

`[VERIFIED-DEVICE]` **ptrace call-injection into `di-camera-app` cannot work.**

- `probe` (attach + detach, no register writes) succeeds — attach is permitted.
- Injecting *any* call — even `getpid`, a pure side-effect-free syscall wrapper —
  crashes the process.

The cause is structural: `PTRACE_ATTACH` stops the main thread wherever it is,
which is almost always inside a blocking syscall in the ecore/glib main loop
(`epoll_wait`/`futex`). Hijacking the thread to run our function and then
restoring its registers corrupts that interrupted syscall, and the app dies.
This is the classic ptrace call-injection hazard, and this app is squarely in
its blast radius. No choice of target function avoids it.

So the delivery mechanism has to be one where **the app runs the call on its own
clean thread**, not a thread we hijacked mid-syscall.

## Next mechanism: LD_PRELOAD at a service restart (no ptrace)

`[VERIFIED-DEVICE, feasibility]` The pieces are all present:

- `di-camera-app.service` has **no `Restart=`**, and takes environment from
  `/run/tizen-mobile-env` (tmpfs, writable). A systemd drop-in under
  `/run/systemd/system/di-camera-app.service.d/` (tmpfs) can add
  `Environment=LD_PRELOAD=…` with no rootfs write.
- `/opt/usr` is `ext4 rw` with no `noexec` — a `.so` placed there can be loaded.
- `systemd-run` exists, so the restart can be launched from a scope that is not
  in the dfmsd cgroup, surviving the restart that would otherwise kill the
  script.
- The SD card mount (`mmcblk1p1` at `/opt/storage/sdcard`) is independent of
  `di-camera-app`, so it stays mounted across the restart and the `.so` can log
  to it.

Plan: a tiny `rvftrig.so` whose constructor spawns a thread; the thread waits
for the app to finish initialising, then calls `btSendEventToUI(8,0,20,0)` via
`dlsym` — the phone's exact call, from a non-main thread, exactly the context
the Bluetooth receive thread uses. The card script installs the drop-in, copies
the `.so`, and restarts `di-camera-app` via `systemd-run`.

This is `tools/card/rvftrig.c` + the `rvf-start.sh` LD_PRELOAD variant.

---

## v8-v10: worker-thread injection, and why ptrace injection is a dead end

| Run | Target | Result |
|---|---|---|
| v8 | worker threads (main pid's tasks), plain waitpid | attach failed `No child process` -- waitpid needs `__WALL` for non-main tids. App did NOT crash (attach never completed). |
| v8+`__WALL` | worker 261 (`shell_di_app`, `do_msgrcv`) | getpid injection **crashed the app** (reboot). |
| v9 | (recon only) | `[VERIFIED-DEVICE]` thread map: every thread is asleep in a syscall. main=poll_schedule_timeout; workers in do_msgrcv or futex_wait_queue_me; none in state R. |
| v10 | worker 262 (`recorder`, `futex_wait_queue_me`) | getpid injection **crashed the app too** (reboot). |

**Conclusion `[VERIFIED-DEVICE]`: simple ptrace call-injection cannot work on this
app.** Every thread is blocked in a syscall, and a hijack+restore corrupts that
syscall's restart on return; the thread then dies, and with it the whole
process. This held for the main thread (poll), a `do_msgrcv` worker, AND a
`futex_wait_queue_me` worker -- the glibc futex EINTR-retry did not save it. No
choice of thread or function avoids it. A syscall-aware injector (à la frida,
moving the thread out of its syscall before the call) would be needed, which is
a large undertaking with no guarantee on this SoC.

### Remaining routes (none is a quick ptrace tweak)
1. **UART console.** `ttyAMA0` runs a getty. Soldering the pads gives a
   persistent root shell in NORMAL mode (not the one-shot script mode), where a
   real cross-compiled `gdb` can do syscall-aware injection, and which is also a
   brick-recovery channel. Hardware work, but the most likely to finally succeed.
2. **Phone-in-the-loop.** An Android phone + the ported Gear 360 Manager starts
   RVF the normal way; the Mac then pulls the stream with the already-built
   `tools/rvf_soap.py` + `tools/ttts.py`. Fastest path to actual video; sidesteps
   the whole injection problem.
3. **Persistent LD_PRELOAD.** Would need the drop-in on a persistent partition
   (script mode reboots and clears /run). That means writing the rootfs (eMMC),
   the one genuinely brick-capable action, and is not recommended.
4. **BlueZ SAP emulation** from a second Linux Bluetooth host sending the real
   `{"execute":"liveview"}` frame. Non-invasive to the app, but a substantial
   SAP/RFCOMM implementation effort.

---

## 2026-07-28 — Live USB shell, and why LD_PRELOAD is also blocked

With the sdb-over-USB root shell (13-usb-console.md), the RVF trigger could
finally be worked live instead of one card per boot. `rvftrig.so` was pushed to
`/opt/usr` (chunked base64 through the shell, md5-verified), a systemd drop-in
`/run/systemd/system/di-camera-app.service.d/rvf.conf` set
`Environment=LD_PRELOAD=/opt/usr/rvftrig.so` + `Restart=always`, and
`systemctl daemon-reload` confirmed both took effect (`systemctl show`).

Then `di-camera-app` was killed to force the preloaded restart. Result, twice
(SIGTERM and SIGKILL): **the whole system rebooted.** `[VERIFIED-DEVICE]`
`/proc/uptime` dropped from 254 s to 41 s; the `/run` drop-in was gone; the
`.so` never logged; `di-camera-app` came back (pid 252) WITHOUT the preload.

The reboot is **not** systemd (`OnFailure=` empty, `WatchdogUSec=0`) and **not**
a process kicking `/dev/watchdog` (no process holds it, before or after).
`di-camera-app` is the camera's sole UI/session app; its death is caught at a
higher level (app-manager / session) that reboots. Taking over `/dev/watchdog`
kicking from the independent sdb shell did **not** prevent it.

**Consequence:** LD_PRELOAD is blocked by the same reboot that clears the only
writable systemd config location (`/run`). To make it work the drop-in (or
`/etc/ld.so.preload`, or the `.service` file) must be **persistent**, i.e. a
rootfs write — the one genuinely brick-capable action — or the reboot-on-death
mechanism must be defeated (not found).

### RVF trigger: full status
Every non-rootfs-write path is now exhausted and verified dead:
- External (OSC commands, SOAP changeToRVF, Street View, Remote control): closed.
- ptrace call-injection (any thread, any function): crashes the app (syscall-restart).
- Non-Bluetooth in-app triggers (D-Bus, SysV, `st`, vconf): none reaches `Start(RVF)`.
- LD_PRELOAD: di-camera-app restart reboots the system, clearing the /run drop-in.

Remaining, all significant: (a) persistent LD_PRELOAD / ld.so.preload via a
rootfs (eMMC) write — brick-capable; (b) a syscall-aware injector (frida-class);
(c) BlueZ SAP emulation feeding the real liveview frame; (d) an Android phone in
the loop (normal RVF) + the already-built `rvf_soap.py`/`ttts.py` on the Mac.

**What IS achieved and solid:** root shell over USB, full firmware teardown,
the recovered SOAP + device description, the tested TTTS demuxer, and a complete
map of the camera. The USB-control question is answered: yes.
