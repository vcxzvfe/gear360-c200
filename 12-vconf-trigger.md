# Can a vconf key start RVF from the shell? — No. (SM-C200)

**Question.** From the confirmed root shell (dfmsd, uid=0), can we start Remote View Finder (RVF —
the mode that binds the live HEVC stream on TCP **7679**) by setting a **vconf key** with
`/usr/bin/vconftool`, causing the already-running `di-camera-app` to enter RVF on its own event
loop — no phone, no restart, no ptrace, no systemd bus?

**Answer: No. There is no such key.** The 7679 bind is **structurally reachable only from the
Bluetooth `EXE_LIVEVIEW` command path**. Not one of `di-camera-app`'s 36 `vconf_notify_key_changed`
registrations — nor anything in the two DLNA libraries — reaches `CUINETFuncDLNA::Start`, the async
worker behind it, or the port bind. Setting a key does nothing useful and some keys would desync the
app's state. **Confidence: HIGH, VERIFIED-BY-OBJDUMP.** No card script is written for this route (see
§7). This supersedes nothing in `10-rvf-trigger.md`; it closes the "non-invasive vconf" option that
`05-experiment-plan.md` left open.

Evidence tags: `[VERIFIED-BY-OBJDUMP]` = read from the camera's own binaries with `/usr/bin/objdump`;
`[INFERRED]` = strongly implied but not a single-instruction fact. Disassembly excerpts are under
`scratchpad/vconf/` (index in §9).

---

## 1. The one fact that settles it: `Start` has exactly 3 callers, all Bluetooth

`[VERIFIED-BY-OBJDUMP]` The RVF start entry `CUINETFuncDLNA::Start(E_UNF_DLNA_FUNC_TYPE, bool)`
@`0x22dedc` is called from **exactly three** `bl` sites in the whole binary, and **all three are
inside** `CUINETFuncBluetooth::handle_bt_app_receive_command` @`0x241b08`:

```
241cac: bl 0x22dedc <CUINETFuncDLNA::Start>   ; cmd 20 EXE_LIVEVIEW -> Start(func=1=RVF)
241d18: bl 0x22dedc <CUINETFuncDLNA::Start>   ; cmd  7 EXE_MOBILE_LINK -> Start(2)
241d58: bl 0x22dedc <CUINETFuncDLNA::Start>   ; cmd 23 EXE_FW_DOWNLOAD -> Start(3)
```

There is **no other reference of any kind** to `0x22dedc`. A raw byte scan of the entire 4.96 MB file
for the little-endian pointer `dc de 22 00` returns **one** hit, at file offset `0x3c4a4` — which lies
inside `.dynsym` (VMA/file 0x1ca70–0x4ecd0) and decodes as `Start`'s own symbol record
(`st_info=0x12` = GLOBAL FUNC, `st_shndx=13` = `.text`, `st_size=0x8c`). So there is **no vtable slot,
no function pointer, no tail-call, no data reference** that could route to `Start` from anywhere else.
`Start` is reachable only by those three direct calls.

The upward chain above `handle_bt_app_receive_command` is equally single-threaded — every edge has
exactly one caller `[VERIFIED-BY-OBJDUMP]`:

```
handle_bt_app_receive_command @0x241b08   <- 1 caller: 0x24263c
  inside handle_bluetooth_callback(int,int,int,char*) @0x2423dc   <- 1 caller: 0x242ddc
    inside CUINETFuncBluetooth::process_event_received @0x242d5c  (INETEventMan dispatch, event type 8
                                                                   = EVT_BT_APP_RECEIVE_COMMAND)
```

`process_event_received` is fed by the SAP/RFCOMM Bluetooth socket receiver (see `10-rvf-trigger.md`
§2.1). No vconf callback appears anywhere on this chain.

## 2. The 7679 bind is downstream of `Start`, and just as gated

`[VERIFIED-BY-OBJDUMP]` The port bind lives in `libdi-network-dlna-rvf.so`:
`StartRVFDevice` @`0x386f8` contains the literal `movweq r3, #0x1dff` (= **7679**) at `0x38a94`.
`di-camera-app` never uses the constant 7679 or 7676 itself — only the RVF library binds those ports.

Tracing backward from the bind, every edge is again single-caller `[VERIFIED-BY-OBJDUMP]`:

```
StartRVFDevice (librvf @0x386f8, binds 7679)
  <- DlnaRVF_ML_FJ_Start (libapi @0x2ab3c)         [the app's only RVF-start export it calls]
       <- di-camera-app CUINETDlnaMan::StartDlna @0x2478d0   [1 caller of the PLT: 0x247a6c]
            <- CUINETFuncDLNA::process_common_activate @0x22dae4  [1 caller of StartDlna: 0x22db68]
                 <- { process_start @0x22df68,  handle_device_conn_state_changed @0x22db9c }
```

`process_common_activate` @`0x22dae4` `[VERIFIED-BY-OBJDUMP]` does **not** call `StartDlna` cold. It
gates on the DLNA function field `m_func` at `this+0x5ec`:

```
22daec: bl is_network_started ; ==0 -> start_network; return
22dafc: bl is_network_connected; ==0 -> send_bt_launch_item(func,100); return
22db08: r5 = [r4,#0x5ec]        ; m_func
22db0c: cmp r5,#1 ; poplt        ; m_func==0 -> RETURN (nothing was requested)
22db14: cmp r5,#2 ; ble 0x22db28 ; m_func 1 or 2 -> proceed to card check + StartDlna
22db4c: r0 = [r4,#0x5e8] ; ==0 -> return
22db64: bl StartDlna(m_func==1, card_error)   ; RVF only when m_func==1
```

So `StartDlna` (hence the 7679 bind) runs **only when `m_func ∈ {1,2}`**. And `m_func` is set to a
value that leads here **only by the `Start` worker**:

- `[VERIFIED-BY-OBJDUMP]` `Start` @`0x22dedc` does not touch `m_func` directly. After the guard
  `get_error_type_to_activate(func) == 100` it posts an async `{func:int, bool}` event via
  `vtable[+0x24]` (`str r5,[sp]; strb r6,[sp,#4]; ldr r12,[r3,#0x24]; blx r12` with `r1=1, r3=8`).
- `[VERIFIED-BY-OBJDUMP + payload-shape match]` `CUINETFuncDLNA::process_start` @`0x22df68` reads that
  exact record (`r7=[r1]` = func, `r8=[r1+4]` = bool), stores `m_func` at `0x22e0d8`
  (`str r7,[r4,#0x5ec]`), then falls straight into `process_common_activate` (`bl 0x22dae4` @`0x22e0ec`).
  `process_start` has **zero direct `bl` callers** — it is invoked only by the event loop dispatching
  the record `Start` posted (`[INFERRED]` routing; the payload layout matches byte-for-byte).

The other two writers of `m_func` are not shell/vconf levers `[VERIFIED-BY-OBJDUMP]`:
`InitValues`/`process_init` (resets), and `dlna_set_operationState(int)` @`0x22f714`, which *can* set
`m_func=1` — but it (a) has **no direct `bl` caller** (it is DLNA-command/event dispatched, reached
only once a UPnP control session already exists, not from vconf and not from the shell) and (b) calls
`ChangeDlnaMode`, **not** `StartDlna`, so it never binds 7679 on its own. The remaining `0x5ec` writes
(`show_sas_golf`) are a **different class** — offset 0x5ec on an unrelated object.

The second `process_common_activate` caller, `handle_device_conn_state_changed` @`0x22db9c`, is driven
by `process_event_received` (network device-connect events), and it too only reaches `StartDlna` when
`m_func` is **already** 1 — i.e. only after a prior `Start(1)`. There is no cold path.

**Net:** binding 7679 for RVF requires `Start(1)` to have run, and `Start(1)` is Bluetooth-command-only.

## 3. The complete `vconf_notify_key_changed` table — 36 sites, 25 keys, none DLNA

`[VERIFIED-BY-OBJDUMP]` There is exactly one `vconf_notify_key_changed` PLT stub (`0xcb8dc`), called
from **36** sites. Full key→callback map in `scratchpad/vconf/notifytable/map.txt`. The 25 distinct
keys, grouped:

| Group | Keys (all `memory/...`) | Callbacks |
|---|---|---|
| Battery/power | `sysman/battery_temperature_warning`, `battery_charge_full`, `battery_health`, `battery_present`, `body_battery_soc`, `battery_charging`, `battery_status_low`, `battery_abnormal_charge_status`, `batt_dischg_voltage_status` | `UI_Vconf_Cb_Battery_*` |
| Card/storage | `sysman/mmc`, `mmc_err_status`, `mmc_format` | `UI_Vconf_Cb_Card_Format`, card mgr |
| USB/MTP/jig | `sysman/usb_status`, `sysman/jig_usb_off_status`, `private/mtp_data_resp`, `sysman/earjack` | `UI_Vconf_Cb_Usb_Manager`, `..._Mtp_data_transfer_Manager`, earjack |
| Factory | `private/pmode_test_result` | `UI_Vconf_Cb_Factory_Accel_Manager` |
| Wi-Fi status | `wifi/state`, `wifi/strength` | `__tvlink_ap_status_changed_cb`, `CAPPGUITVLinkState::wifi_status_changed_cb`, `CAPPGUIQuickPanelState::wifi_*`, `UI_Wifi_Direct_Create`, `UI_WiFi_Soft_Ap_Create` |
| AP-setting | `ap_setting/state` (4 sites), `ap_setting/request_type` (1) | `UI_Operate_Launch_AP_Setting_App` (anon cb), `UI_Operate_After_Exit_AP_Setting_App`, QuickPanel |
| BT / NFC / cloud | `bt/state`, `bluetooth/passkey`, `nfc/nx1_tag_event`, `app/cloud_file` | QuickPanel bt cb, `__vconf_cb_bt_passkey`, `__callback_nfc_tagging`, `Ui_Controll_Cloud_Vconf` |

`[VERIFIED-BY-OBJDUMP]` **No registered key mentions dlna / rvf / liveview / evf**, and **none of these
callbacks is, or calls, `Start` / `process_start` / `process_common_activate` / `dlna_set_operationState`
/ `StartDlna` / `DlnaRVF_ML_FJ_Start`.** (They cannot: §1–§2 already show those sinks have no vconf
predecessor.)

## 4. Verdict on each anchor key from the brief

Rodata VMAs verified; the region load shift is VMA − file_off = `0x8000` (`.rodata` VMA 0x340300 =
file 0x338300).

| Key | rodata VMA | notify-registered? | Role `[VERIFIED-BY-OBJDUMP]` | Reaches RVF? |
|---|---|---|---|---|
| `memory/app/wifi_evf` | 0x345390 | **No** (0 sites) | App-**written** status flag ("in wifi EVF"); set 1 in `UI_TV_Link_Start`/`UI_PB_DrawShare_Popup`, reset 0 at boot; read as a **guard** in `UI_TV_Link_Start`, `UI_Start_Boot_Liveview_By_Usb_Ptp_And_Sdb`. All refs are `vconf_get/set_int`. | **No** |
| `memory/app/softap_active` | 0x344a04 | **No** | App-written SoftAP status flag (`UI_WiFi_Soft_Ap_Create`) | **No** |
| `memory/app/direct_active` | 0x3449e8 | **No** | App-written Wi-Fi-Direct status flag (`UI_Wifi_Direct_Create`) | **No** |
| `memory/app/boot_mode` | 0x3480dc | **No** | App-written; boot/restart only | **No** |
| `memory/ap_setting/state` | 0x3457ac | **Yes** (4 sites) | Watched. Callback path does Wi-Fi + **TV-Link** bring-up only (§5). Never calls `Start`. | **No** |
| `memory/ap_setting/request_type` | 0x345774 | **Yes** (1 site) | QuickPanel GUI refresh (`bt/wifi_status_changed_cb`) | **No** |
| `memory/dfms/mode_changed_done` | 0x34a5bc | **No** | App-**written** "mode change done" signal (`UI_Draw_Modedial_BG`) | **No** |
| `memory/app/is_called_custom_mode` | 0x347eac | **No** (`bool`) | App-written soft-keyboard flag (`CAPPGUICustomView`) | **No** |

The five `app/*` + `dfms/*` + `is_called_custom_mode` keys are **outputs the app produces**, not inputs
it watches — the app is their *producer*. Setting them from the shell fires **no callback** and only
lies to the app's own guards.

## 5. The closest candidate (`ap_setting/state`) still does not start RVF

`[VERIFIED-BY-OBJDUMP]` `ap_setting/state` is the only watched key with any Wi-Fi/live semantics. Its
transition-to-1 callback `UI_Operate_After_Exit_AP_Setting_App` @`0x1820ec` calls
`UI_Manage_After_AP_Setting` @`0x11d084`, whose **complete** set of `bl` targets is: `UI_TV_Link_Start`,
`UI_Launch_WiFi_App_Service`, `UI_Set_Mask_Evf_For_Wifi`, `UI_Operate_Launch_AP_Setting_App`,
`UI_Manage_App_Relaunch`, plus display/timer/sensor/battery helpers. **No `CUINETFuncDLNA::Start`, no
`process_common_activate`, no `StartDlna`, no `DlnaRVF*`.** It brings up Wi-Fi and the **TV-Link/mobile
mode** — a *different* DLNA mode that does **not** bind 7679. (And `UI_TV_Link_Start` cannot secretly
reach `Start`: `Start`'s only 3 callers are in the BT handler — §1.) The UI symbols one might hope for —
`UI_RVF_Start` @`0xff188`, `UI_ML_Start` @`0xff18c`, `UI_Operate_Liveview_Start` @`0x18243c` — are all
empty `bx lr` **stubs**.

## 6. The DLNA libraries are vconf-blind

`[VERIFIED-BY-OBJDUMP]` Neither `libdi-network-dlna-api.so` nor `libdi-network-dlna-rvf.so` imports any
`vconf_*` symbol, and neither contains the strings `wifi_evf` / `ap_setting` / `memory/*`. They cannot
watch a key; they are pure slaves to `di-camera-app`'s exported `DlnaRVF_*` calls. Also checked: the
only app-reachable function that binds 7679 is `DlnaRVF_ML_FJ_Start` (→ `StartRVFDevice`);
`DlnaRVFSendUserStartEvent` (called from `UI_Wifi_Taggo_Destructor` / `handle_dlna_callback`) only sets
an event flag in an **already-running** RVF session (`RVFAppSetEventFlag`) and does **not** bind — so it
is not an alternate path either. (`DlnaRVFStart` @0x27614 also reaches `StartRVFDevice` inside libapi,
but `di-camera-app` never calls it.)

## 7. Why no card script, and the hardware risk if a key is set anyway

Per the task rule (write the trigger script only if a key reaches RVF with medium+ confidence): **no key
reaches RVF, so no `rvf-start.sh` is written for this route.** The existing `tools/card/rvf-start.sh`
(the LD_PRELOAD/kill approach) and `tools/card/rvf-inject.c` (ptrace) belong to the in-process
workstream and are **left untouched**.

Setting the anchor keys on the bench is not just useless, it is mildly risky and must not be done as a
"trigger":
- `wifi_evf=1`, `softap_active=1`, `direct_active=1` make the app **believe** Wi-Fi EVF / SoftAP /
  Wi-Fi-Direct is active when it is not → its own guards (`UI_TV_Link_Start`,
  `UI_Start_Boot_Liveview_By_Usb_Ptp_And_Sdb`) branch on stale state → possible confused link/UI state,
  **zero** chance of RVF.
- `ap_setting/state` **is** watched, so writing it actively **fires** the AP-setting-exit flow
  (Wi-Fi app launch, TV-Link start, EVF mask) with no peer present → confused link/UI state, still no
  7679.

Inspection reads are harmless: `vconftool get <key>`.

## 8. Recommended next step

The non-invasive vconf option is **conclusively dead**. The 7679 bind is gated behind `Start(1)`, which
is only reached by the Bluetooth `EXE_LIVEVIEW` command dispatched through the in-process event manager.
The remaining shell-side routes are the in-process ones already documented:

1. **In-process call injection** (`10-rvf-trigger.md`): fire `handle_bt_app_receive_command(singleton,
   0, 20, singleton)` (F2, fixed `ET_EXEC` addresses) or `btSendEventToUI(8,0,20,0)` (F1). The open
   blocker is that main-thread hijack corrupts the interrupted syscall. **Useful refinement from this
   analysis:** the heavy work is *not* done synchronously in `Start` — `Start` only posts a
   `{func=1,bool}` record via `vtable[+0x24]`, and the app's own event loop later runs `process_start`
   → `process_common_activate` → bind. So an injected call to `Start` (F3) / the BT handler (F2) needs
   only to *survive long enough to enqueue the post*; injecting onto a **non-main worker thread**
   (leaving the main event loop free to service the post) is the variation most likely to avoid the
   observed crash. Worth trying before abandoning ptrace.
2. **LD_PRELOAD at relaunch** (existing `rvf-start.sh` v7): drop-in `Restart=always` +
   `kill di-camera-app`, constructor calls the same command. Blocked previously only by the
   restart/bus, which the kill-based v7 works around; if a kill reboots the whole system, gate the
   preload constructor so it self-arms once.
3. **Bluetooth transport emulation** (out of the "no phone" spirit but genuinely non-invasive to the
   app): a Linux host running BlueZ can present the phone-side SAP/RFCOMM profile and send the real
   `{"execute":"liveview"}` frame `di-camera-app` already listens for — no injection, no restart. This
   is the cleanest route if a second Bluetooth host is acceptable.

## 9. Evidence index (`scratchpad/vconf/`)

- `di-camera-app.dis`, `libapi.dis`, `librvf.dis` — full LLVM objdump disassembly.
- `notifytable/map.txt` — all 36 `vconf_notify_key_changed` sites → key + callback.
- `extract_notify.py` — ELF-aware extractor (section-header VMA→file translation + pool/symbol resolve).
- `evidence/CALLGRAPH_start_chain.txt` — caller lists for `Start`, the BT handler,
  `process_common_activate`, `StartDlna`, `DlnaRVF_ML_FJ_Start@plt`.
- `evidence/process_common_activate.asm` — the `m_func`-gated activation.
- `evidence/process_start.asm` — the async worker that sets `m_func` and calls activate.

---

**Bottom line.** `[VERIFIED-BY-OBJDUMP]` No vconf key — watched or not — reaches
`CUINETFuncDLNA::Start`, the async worker, or the `StartRVFDevice` 7679 bind. The RVF bind is
Bluetooth-`EXE_LIVEVIEW`-command-only. Do **not** set any vconf key on the bench hoping to start RVF;
`vconftool get` for inspection is fine. Fall back to in-process injection (with the worker-thread
refinement), LD_PRELOAD-at-relaunch, or BlueZ SAP emulation.
