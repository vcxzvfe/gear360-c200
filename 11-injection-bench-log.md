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
