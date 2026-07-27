# Starting RVF from a root shell — no phone (SM-C200)

**The one remaining question, answered.** From a root shell, Remote View Finder (RVF — the mode
that binds the HEVC stream on TCP 7679) is started by making the *already running* `di-camera-app`
process execute its own command entry point with command id **20 = `EXE_LIVEVIEW`**. That value,
and the whole chain from it to the 7679 bind, are verified by objdump against the camera's own
binaries. There is **no pure dbus-send / st / socket command** that does it: the command path
lives entirely inside `di-camera-app` and normally arrives over SAP/RFCOMM from the phone. So the
trigger is a small **ptrace call injected into the live process**, carried onto the SD card as a
static ARM helper.

Evidence tags: `[VERIFIED-BY-OBJDUMP]` (read from the camera's binaries with `/usr/bin/objdump`),
`[INFERRED]`, `[UNKNOWN]`. Disassembly excerpts are saved under `scratchpad/rvftrig/` (index in
`synth/SYNTHESIS.md`); the card files are `tools/card/rvf-start.sh` and `tools/card/rvf-inject.c`.

---

## 1. THE ANSWER

Make `di-camera-app` (PID = `pidof di-camera-app`) execute, in-process:

```
btSendEventToUI(8, 0, 20, 0)
```

`[VERIFIED-BY-OBJDUMP]` This is **byte-for-byte the call the phone's "execute liveview"
produces**. `btSendEventToUI` is exported by `libdi-network-bt-app.so.0.2.72`
(`00008de0 g DF .text btSendEventToUI`), which is linked into `di-camera-app`
(`NEEDED libdi-network-bt-app.so.0`). The emit site inside `bt_handle_received_data` is exactly:

```
1081c: 2100  movs r1,#0
1081e: 463a  mov  r2,r7     ; r7 = cmdId = 20 for {"execute":"liveview"}
10820: 2008  movs r0,#8     ; 8 = EVT_BT_APP_RECEIVE_COMMAND
10824: 460b  mov  r3,r1     ; 0
10826: blx   btSendEventToUI@plt        -> btSendEventToUI(8, 0, 20, 0)
```

Because a separate process cannot call an in-process function, and the device has **no
gdb/gdbserver/frida** (rootfs search: only `gdbus`, `dbus-send`), the call is made with a small
**ptrace injector** placed on the card. Core of it:

```sh
PID=$(pidof di-camera-app)
BASE=$(awk '/libdi-network-bt-app\.so/ && $3=="00000000"{print $1;exit}' /proc/$PID/maps | cut -d- -f1)
FUNC=$(printf '0x%x' $((0x$BASE + 0x8de0)))   # file offset 0x8de0, THUMB
/tmp/rvf-inject "$PID" thumb "$FUNC" 8 0 20 0
```

**The integer is pinned, not guessed — two independent confirmations of 20:**

1. `[VERIFIED-BY-OBJDUMP]` **di-camera-app**: `ToString_BT_COMMAND` resolves `enum 20 =
   "EXE_LIVEVIEW"`, and `handle_bt_app_receive_command` routes command 20 to the handler that
   calls `CUINETFuncDLNA::Start(func=1=RVF)` (§2.2). `enum 21 = "DIS_LIVEVIEW"` routes to a *stop*
   handler — so 21 is the opposite of what we want.
2. `[VERIFIED-BY-OBJDUMP]` **libdi-network-bt-app**: `bt_get_cmdId(description="liveview",
   key="execute")` returns **20** (`0x14`) (§2.4).

Fallback if the `.so` base is unavailable — `di-camera-app` is `ET_EXEC` (fixed runtime
addresses), so this needs no `/proc/maps` at all:

```
handle_bt_app_receive_command(this=0x005027f4, 0, 20, 0x005027f4)   # ARM, func @ 0x241b08
```

`0x005027f4` is the `CUINETFuncBluetooth` singleton `this` (§3, F2).

---

## 2. WHY it works — the chain to the 7679 bind

`[VERIFIED-BY-OBJDUMP]` `di-camera-app` **links** `libdi-network-bt-app.so.0`, so the socket
receiver, `btSendEventToUI`, and the whole dispatch run **inside the one `di-camera-app` process**.
`bt_le_manager` is a separate BLE process and does not link the bt-app lib. The inbound command
transport is **SAP-over-RFCOMM** (`bt_socket_connect_rfcomm`, `bt_sap_enable`,
`bt_socket_received_cb`) — a Bluetooth socket a shell cannot write to. Hence in-process injection.

### 2.1 `btSendEventToUI(8,0,20,0)` → the dispatcher, with no remap

`[VERIFIED-BY-OBJDUMP]` `btSendEventToUI` @`0x8de0` (THUMB) forwards its 4 args **unchanged** to
the callback di-camera-app installed (stored at `global+0x8bc`, NULL-checked):

```
902a: ldr.w r4,[r3,#0x8bc]      9032: mov r0,r5(=8)   9034: mov r1,r7(=0)
9036: mov r2,r9(=20)  9038: mov r3,r10(=0)  903a: blx r4
```

The callback is `CUINETDevBluetooth::handle_bluetooth_callback(ST_UND_BLUETOOTH_CALLBACK_INFO&)`
@`0x24c87c`; **eventType 8 (`EVT_BT_APP_RECEIVE_COMMAND`) hits the default arm** →
`broadcast_bt_callback` @`0x24c2dc` → `INETEventMan` → `CUINETFuncBluetooth::process_event_received`,
which reads the event record at block `0x242dc4`: `a1=evt[+4]=eventType(8)`, `a3=evt[+0xc]=command(20)`,
`payload=evt[+0x14]`, and calls `handle_bluetooth_callback(int,int,int,char*)` @`0x2423dc`. That
dispatches on `a1=eventType` (`sub r3,r5,#5; cmp #75; ldrls pc,…`, table @`0x2424b4`); index 3
(eventType 8) = `0x24262c` → `bl 0x241b08 handle_bt_app_receive_command` with `r2=a3=20`.
`[VERIFIED-BY-OBJDUMP]` The command byte reaches the dispatcher exactly as sent — no translation
table anywhere.

### 2.2 Dispatcher: command 20 → `CUINETFuncDLNA::Start(func=1=RVF)`

`[VERIFIED-BY-OBJDUMP]` `handle_bt_app_receive_command` @`0x241b08` (ARM); command = 2nd int arg
(`mov r6,r2`), jump table index = command − 7:

```
241bc8: sub r3,r6,#7   241bcc: cmp r3,#27   241bd0: ldrls pc,[pc,r3,lsl#2]   ; table @0x241bd8
241c0c: 00241c48   ; idx 13 (cmd 20) -> handler 0x241c48
241c10: 00241d60   ; idx 14 (cmd 21) -> STOP handler (SendBTExitItem)
```

Handler `0x241c48` (cmd 20): after `IsStartedFunc(1)`/`IsStartedFunc(3)==0` guards,

```
241ca0: ldr r0,[r4,#0x664]   ; m_dlna
241ca4: mov r1,#1            ; func = 1 = RVF
241ca8: ldrb r2,[r4,#0x662]  ; runtime bool ("no card"), not a constant
241cac: bl 0x22dedc <CUINETFuncDLNA::Start>
```

`[VERIFIED-BY-OBJDUMP]` `func=1` cross-checks against siblings in the same function: cmd 7
(`EXE_MOBILE_LINK`)→`Start(2)`, cmd 23 (`EXE_FW_DOWNLOAD`)→`Start(3)` — matching the export name
`DlnaRVF_ML_FJ_Start` (RVF=1/ML=2/FJ=3).

### 2.3 `Start` → `StartDlna` → `DlnaRVF_ML_FJ_Start` → bind 7679

`[VERIFIED-BY-OBJDUMP]` `CUINETFuncDLNA::Start` @`0x22dedc` posts an internal `{func,bool}` event
via `vtable[+0x24]` (`ldr r12,[r3,#0x24]; blx r12`). `[INFERRED]` that async post is serviced on
the app event loop and reaches `CUINETDlnaMan::StartDlna` @`0x2478d0` (the only non-static edge).
Then static: `StartDlna` `bl DlnaRVF_ML_FJ_Start@plt` (@`0x247a6c`) → `DlnaRVF_ML_FJ_Start`
@`0x2ab3c` `bl StartRVFDevice@plt` (@`0x2ad3c`) → **StartRVFDevice binds TCP 7679** (anchor,
confirmed on the live camera).

### 2.4 What the phone sends (and the 20-vs-21 correction)

`[VERIFIED-BY-OBJDUMP]` `bt_handle_received_data` parses `{"…":"execute":"liveview"}` and calls
`bt_get_cmdId(description="liveview"@rodata 0x1f19c, key="execute"@rodata 0x1dab8)` @`0x17b78`.
It gates on `strstr(key,"execute")`: key contains "execute" → **execute chain**, else **dismiss
chain**. Following the `cbz` fall-through targets:

- execute chain … → `0x17cb6`: `strstr("liveview",desc)` → `movs r0,#0x14` = **20**.
- dismiss chain … → `0x17ca6`: `strstr("liveview",desc)` → `movs r0,#0x15` = 21.

So `{"execute":"liveview"}`→**20**→RVF start; `{"dismiss":"liveview"}`→21→stop. `[VERIFIED-BY-OBJDUMP]`
Consistent with di-camera-app's enum (`EXE_LIVEVIEW=20`, `DIS_LIVEVIEW=21`); lib and app share one
enum, no remap. (An earlier teardown reported execute→21 — it read the two interleaved `strstr`
chains backwards. Both sites point at the same "liveview" string `0x1f19c`; only the chain differs.)

---

## 3. FALLBACKS, ranked

All routes are in-process ptrace calls (the only kind that can work — §5), all with id **20**. The
card script tries F1 then F2 automatically and records which one bound 7679.

- **F1 — `btSendEventToUI(8,0,20,0)`** (THUMB, `<so base>+0x8de0`). *Primary.* The phone's exact
  call; goes through the real event-manager hand-off so it runs on the correct thread whichever
  thread we hijack. Needs the `.so` base (trivial from `/proc/PID/maps`) and the callback installed
  (it is, once BT init ran — the camera advertises for the phone from boot). If the callback is
  NULL it no-ops (checked @`0x9030`) → F2.
- **F2 — `handle_bt_app_receive_command(0x005027f4,0,20,0x005027f4)`** (ARM, func @`0x241b08`).
  *Zero-discovery.* `ET_EXEC` fixed addresses; `this` = fixed singleton `0x005027f4`
  (`CUINETFuncBluetooth::Inst()` @`0x23a4e4` returns the static at `0x005027f4`, guard @`0x5027f0`).
  4th arg is a readable pointer, not dereferenced on the liveview slot — reuse `0x005027f4`. Calls
  the dispatcher directly; `Start` still async-posts the heavy work.
- **F3 — `CUINETFuncDLNA::Start(CUINETFuncDLNA::Inst(),1,0)`** (Inst @`0x221298`, Start @`0x22dedc`).
  Bypasses the `IsStartedFunc` guards. `[INFERRED]` same `StartDlna` post.
- **F4 — `DlnaRVF_ML_FJ_Start(a,b,c)`** @`0x2ab3c` (exported C, 3 args). Reaches
  `StartRVFDevice`/7679 but `[UNKNOWN]` args and may start only the UPnP server, not the encoder
  pipeline F1–F3 set up. Last resort.

**Dead ends `[VERIFIED-BY-OBJDUMP]` (do not spend bench time):** D-Bus `org.bt.app_event` emit
(carries only `AppGattConnectionState`/`AppLEAdapterState`; subscriber drops other members);
D-Bus `app_service_request` (outbound app→`bt_le_manager`); SysV queues `0x160/0x161/0x162`
(`bt_api_manager` handles only HID/bond/discovery `0x1000–0x1007`; `bt_cmd_process` is outbound;
`bt_handle_received_data` has one caller, the RFCOMM socket cb `0x1149e`); `st` (no rvf verbs).

---

## 4. THE CARD SCRIPT

Four files at the FAT32 card root. Obey the card-safety rules in `09-root-procedure.md` (no
`C200*` file, no `.bin`, no block-device writes). The injector is a foreign binary — allowed for
Stage B; it is not firmware-shaped and the `.sh` never flashes.

**Control files — byte-exact, one trailing `\n`, no CRLF, no trailing space:**

`info.tg` (8 bytes, hex `72 76 66 2e 61 64 6a 0a`):
```
rvf.adj
```
`rvf.adj` (35 bytes, hex `73 68 65 6c 6c 20 73 63 72 69 70 74 20 2f 6d 6e 74 2f 6d 6d 63 2f 72 76 66 2d 73 74 61 72 74 2e 73 68 0a`):
```
shell script /mnt/mmc/rvf-start.sh
```

**`rvf-inject`** — build `tools/card/rvf-inject.c` on a Linux host, static so the device
libc/float ABI is irrelevant:
```
arm-linux-gnueabi-gcc -static -O2 -march=armv7-a -o rvf-inject rvf-inject.c
# docker: docker run --rm -v "$PWD":/w -w /w debian:bookworm sh -c \
#   'apt-get update && apt-get install -y gcc-arm-linux-gnueabi && \
#    arm-linux-gnueabi-gcc -static -O2 -march=armv7-a -o rvf-inject rvf-inject.c'
```
The injector attaches, sets `r0–r3`, sets `pc=func` (THUMB via CPSR.T for F1, ARM for F2), sets
`lr=0` so the call returns into a fault it catches, reads `r0`, then **restores the original
registers and detaches** — leaving the process exactly as found. Full source + rationale in the
file; it writes nothing to any block device.

**`rvf-start.sh`** — the exact card script is `tools/card/rvf-start.sh`. Run by `dfmsd` as root it:
1. records `id` and a baseline `netstat -lntp` to `/mnt/mmc/rvf-out/`;
2. finds `pidof di-camera-app`, saves `/proc/PID/maps` and the target's SMACK label;
3. best-effort relaxes ptrace gating: `echo 0 > /proc/sys/kernel/yama/ptrace_scope` and sets our
   own SMACK label to the target's (both silent if not permitted);
4. copies `rvf-inject` from the (noexec) card into tmpfs (`/tmp`, RAM) and `chmod +x`;
5. **fires F1** (`btSendEventToUI(8,0,20,0)` at the resolved `.so` base), waits, checks `:7679`;
6. if not up, **fires F2** (`handle_bt_app_receive_command(0x005027f4,0,20,0x005027f4)`), checks;
7. writes a final `netstat -lntp`, greps `:7679`/`:7676`, records the winning candidate, and
   `touch`es `DONE`.

It writes only to `/mnt/mmc/rvf-out` (the card) and `/tmp` (RAM); no `dd`/`mount`/`fw_upgrade`,
no `/dev/mmcblk*`. **Reversal:** delete `info.tg` from the card; the ptrace call is reverted before
exit and tmpfs is cleared on reboot, so nothing on the camera persists.

---

## 5. WHAT REMAINS UNKNOWN — and how the card run settles it

1. **Does root ptrace work under Tizen SMACK?** `[UNKNOWN]` — the single real gate. Root has
   `CAP_SYS_PTRACE`, but SMACK may still deny `PTRACE_ATTACH` (EPERM). The script's yama+SMACK
   relaxation is best-effort. **Resolution:** `10-c1-inject.txt` shows the injector's stderr. If it
   reads `PTRACE_ATTACH … EPERM`, ptrace is blocked and the only remaining route is
   LD_PRELOAD-at-launch (restart `di-camera-app` under a preload that calls the trigger from a
   constructor) — invasive, out of scope for the zero-write recon, noted here as the escalation.
2. **Is the command value 20 or could a subtlety flip it?** *Pinned to 20* by two binaries (§1),
   so the script does **not** brute-force 20-vs-21 (21 = `DIS_LIVEVIEW` would *stop* RVF). If both
   F1 and F2 report `OK r0=…` yet 7679 stays down, the value is right and the block is elsewhere —
   see item 3.
3. **The activation guard `get_error_type_to_activate(RVF)`.** `[INFERRED]` `CUINETFuncDLNA::Start`
   only posts the start event when this returns 100 (OK); otherwise it raises an error launch item.
   On an idle camera in normal preview it should be 100, but mode/storage/battery could gate it.
   **Resolution:** if the injector says `OK` but 7679 is absent, the call ran and RVF was gated —
   re-run with the camera in plain capture mode, card inserted, battery healthy.
4. **F1 `.so` base vs the fixed F2 path.** If `/proc/PID/maps` layout differs from the assumption
   (text segment at file offset 0), F1's `FUNC` is wrong; F2 (all fixed addresses) is immune and is
   why it exists. The `03-maps.txt` dump on the card lets us re-derive the base offline if needed.

**Bottom line:** command id **20** and the chain to the 7679 bind are settled. The only open
variable is whether the device permits root ptrace; one Stage-B card run answers it read-from-the-card,
with the injected call fully reverted regardless of outcome.
