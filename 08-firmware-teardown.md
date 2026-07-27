# Gear 360 (SM-C200) — Firmware Teardown

**Subject:** `C200GLU0AQK1.bin`, 279,094,189 bytes, SHA256 `150bc483…c48db` (re-verified unchanged
after all work — the source file was never opened for writing).
**Goal:** receive, on a Mac, the live HEVC stream the camera already produces, without the dead
Samsung Android app.
**Date:** 2026-07-27.

---

## Evidence tags

Every factual statement below carries one:

| Tag | Meaning |
|---|---|
| `[VERIFIED-EXTRACTED]` | Read out of the decompressed firmware (rootfs binaries, kernels, partitions) on this machine. Reproducible from the artifacts listed in the appendix. |
| `[VERIFIED-SOURCE]` | Read out of Samsung's GPL source release for SM-C200. |
| `[COMMUNITY]` | Third-party claim (XDA, GitHub). Not verified against this hardware or this image. |
| `[INFERRED]` | A reasoned conclusion from verified facts, or a single-sourced disassembly result that was not independently reproduced. Flagged as such wherever it matters. |
| `[UNKNOWN]` | Not determined. |

**The methodology rule that governs everything here:** in the *raw* `.bin`, the payload is
compressed (entropy 6.99–7.96 bits/byte), so a string hit is evidence but a string *miss* is
worthless. Unpacking inverted that — `fw_upgrade_start` went 0 → 18 hits, `make_snapshot` 0 → 39.
`[VERIFIED-EXTRACTED]` Every negative claim in this report is made against the *decompressed*
tree, never the raw image.

**One trap worth naming up front:** macOS BSD `grep -rl` silently skips binary files. The extracted
rootfs looks empty of every RVF string unless you use `grep -a` or scan in Python. That produced a
false negative during this work. `[VERIFIED-EXTRACTED]`

---

# 1. What the firmware told us about how this machine works

## 1.1 The single fact that reframes the problem

`[VERIFIED-EXTRACTED]` **There is no streaming daemon.** Ports 80, 7676, 7679 and 9001 are all
bound by *one* process:

```
/usr/apps/com.samsung.di-camera-app/bin/di-camera-app
```

started by `di-camera-app.service`. A `DT_NEEDED` walk over all 1,659 ELF objects in the rootfs
shows it is the **only** binary linking `libdi-network-dlna-api.so`,
`libdi-network-bt-app.so.0` and `libmmfcore.so`. No systemd unit anywhere references `dfmsd`, and
no unit or script can start "the streamer" independently.

So "start the stream" is not "launch a service." It is "drive the camera application into Remote
View Finder state." That is the whole problem, and it is why no amount of port-poking from outside
was ever going to work.

## 1.2 What starts RVF

`[VERIFIED-EXTRACTED]` The activation chain, recovered from ARM/Thumb disassembly and string
cross-referencing:

```
BT accessory message  {"properties":{"msgId":"cmd-req", ... "execute":"liveview"}}
   -> libdi-network-bt-app.so parses JSON, maps to E_BT_COMMAND EXE_LIVEVIEW = 20
   -> di-camera-app  CUINETFuncBluetooth::handle_bt_app_receive_command  @0x241b08
        (jump table @0x241bd8, index = cmd - 7; slot 20 -> handler @0x241c48)
   -> CUINETFuncDLNA::Start(func = 1 = RVF)   @0x22dedc
   -> CUINETDlnaMan::StartDlna                @0x2478d0
   -> DlnaRVF_ML_FJ_Start        (libdi-network-dlna-api.so)
   -> StartRVFDevice             (libdi-network-dlna-rvf.so @0x386f8)
   -> RVFAppInitialize -> ServerToHandleFileTransfer::StartHTTPServer(7679)
                       -> DMSAppSetHTTPStreamingPort
      RVFAppStart
```

`E_UNF_DLNA_FUNC_TYPE` = {1 = RVF, 2 = ML, 3 = FW_DOWN}, read from the
`ToString_E_UNF_DLNA_FUNC_TYPE` table @0x22d750. `[VERIFIED-EXTRACTED]`

I independently confirmed the endpoints of this chain: `EXE_LIVEVIEW` and `DIS_LIVEVIEW` exist as
single string-table entries in `di-camera-app` (@0x38b8ac / @0x38b8bc), `DlnaRVF_ML_FJ_Start`
appears once (@0x4a47e), `CUINETFuncDLNA` 207 times, and `is_valid_liveview_command` /
`start_liveview` are present as symbols (@0x387408, @0x387424). `[VERIFIED-EXTRACTED]`

> **Honesty note the parent must not skip.** I confirmed every *symbol address* and every adjacent
> *string literal* cited above. I could **not** independently reproduce the **call edges** — my own
> capstone pass desynced on these libraries (717 BLs decoded, only 1 landing in a 961-entry PLT,
> which is an implausible result and means my disassembler, not the original agent's, was wrong).
> Treat the arrows in that diagram as **strong but single-sourced**. `[INFERRED]`

**The complete BT command vocabulary** (I dumped the contiguous `.rodata` table at
`libdi-network-bt-app.so.0.2.72` @0x1f19c myself, and it is *richer* than earlier analysis
reported):

```
q-autoshare  autoshare  rvf  mobilelink  app  selectivepush  remote-shot  pro-suggest
bt-off  liveview  config  fw-download  format  reset_device  reset-connection  reset-all
power-save-off  timer  "timer stop"  "timer end"  capture  "capture end"  record
"record end"  disconn  get  set  single
```
`[VERIFIED-EXTRACTED]` Earlier analysis listed 17 of these; there are more. Note `reset_device`
uses an **underscore** while every sibling uses a hyphen — a real Samsung typo, and exactly the
kind of detail that breaks a hand-written client.

The JSON envelope nests one level: `{"properties":{"msgId":"…"}}`, not `msgId` at the root.
`[VERIFIED-EXTRACTED]` (from `bt_get_msgId_obj` @0x17ec4, two chained
`json_object_object_get` calls: `properties` @0x1f3bc then `msgId` @0x1f3c8).

Transport: Samsung Accessory Protocol over Bluetooth RFCOMM. The camera registers ASP-ID
`/system/DI_360_2D` (agent `DI_360_2DApp`), advertises as `Gear 360 (%s)`, and the SAP service
UUIDs are `a49eb41e-cb06-495c-9f4f-aa80a90cdf4a` and `a49eb41e-cb06-495c-9f4f-bb80a90cdf00`
(both re-read by me from `libsap-api.so.1.0.0` @0x41070 and @0x410f8). The daemon is
`/usr/bin/sap-server`, started by `sap.service`. `[VERIFIED-EXTRACTED]`

## 1.3 What binds 7679

`[VERIFIED-EXTRACTED]` `ServerToHandleFileTransfer::StartHTTPServer`, inside
`libdi-network-dlna-rvf.so`, called from `RVFAppInitialize`, reachable only via `StartRVFDevice`.
The port number is **not** hardcoded at the call site: it is read from
`<HTTPStreamingPort>` in `/mnt/mmc/.config/UPnPConfig.xml`, whose default template is embedded in
`libdi-network-dlna-stack.so` @0x143fef. I dumped that block verbatim:

```xml
<UPnPConfig>
<WebServerPort>5215</WebServerPort>
<UPnPServerPort>5216</UPnPServerPort>
<HTTPTCPServerPort>7676</HTTPTCPServerPort>
<HTTPUDPServerPort>24234</HTTPUDPServerPort>
<HTTPMulticastServerPort>1900</HTTPMulticastServerPort>
<HTTPMulticastEventServerPort>7900</HTTPMulticastEventServerPort>
<HTTPStreamingPort>7679</HTTPStreamingPort>
<OsVersion>Windows</OsVersion>
```
`[VERIFIED-EXTRACTED]` (The `<OsVersion>Windows</OsVersion>` is Samsung's, not a transcription
error — this is the AllShare desktop stack transplanted into a camera.)

### Correction — an earlier claim was overstated

Earlier analysis stated flatly that **"the HTTP GET itself starts the encoder."** That is
**overstated and partly contradicted by the bench data.** `RVFStreamingThruGet::HandleHeader`
(@0x99d54) does *contain* a path to `setStreamingQuality` → `start_RVF_streaming` →
`CDSRVF_Mpegfunc_mpeg_start`, and those symbols exist at the cited addresses. But 7679 is already
**listening** in RVF mode before any client connects, so the socket bind is demonstrably *not*
caused by the GET, and whether the encoder is idle until the GET was never resolved from
disassembly. `[INFERRED]`

**Correct statement:** the GET handler contains a code path that can invoke
`start_RVF_streaming`; whether the encoder is dormant beforehand is `[UNKNOWN]`. Do not design a
trigger sequence that assumes the encoder only wakes on connect.

## 1.4 The practical payoff — can we start the stream without the phone?

### Straight answer

**Not yet with a single command — but the teardown moved this from "we don't know how" to "we know
exactly which one layer is missing," and everything downstream of that layer is now fully
specified and ready to fire.**

Here is the honest decomposition.

#### What is now solved and immediately usable

**(a) The SOAP request that switches the camera into RVF is fully recovered.** This was never
captured on the wire before. All of it came out of `libdi-network-dlna-rvf.so`; I re-read every
piece myself.

Device description (@0x7778c), verbatim:

```xml
<friendlyName>[Camera]Gear 360</friendlyName>
<modelName>360</modelName>
<serviceType>urn:schemas-upnp-org:service:ContentDirectory:1</serviceType>
<controlURL>/smp_3_</controlURL>
<eventSubURL>/smp_4_</eventSubURL>
<SCPDURL>/smp_5_</SCPDURL>
```

The action, from the ContentDirectory SCPD (@0x7aaf9), verbatim:

```xml
<action>
  <name>SetOperationState</name>
  <argumentList>
    <argument><name>StateEvent</name><direction>in</direction>
      <relatedStateVariable>ChangeStateEvent</relatedStateVariable></argument>
    <argument><name>ChargingStatus</name><direction>out</direction>
      <relatedStateVariable>RVF_CHARGING_STATUS</relatedStateVariable></argument>
  </argumentList>
</action>
```

`[VERIFIED-EXTRACTED]` **Important gotcha:** the SCPD declares `ChangeStateEvent` as
`<dataType>ui4</dataType>`, but the handler
(`UPnPCDSRVFSetOperationState::get_operation_state_index` @0x5fce8) does a **case-insensitive
string** compare against `changeToML` (@0x862f8, → index 0) and `changeToRVF` (@0x86304, → index
1). Send the string, not a number. The SCPD is lying.

The wire format, from the request template in `libdi-network-dlna-stack.so` @0x14e181
(I dumped it verbatim):

```
POST %s HTTP/1.1
Accept: */*
User-Agent: %s
Host: %s
SOAPACTION: "%s#%s"
CONTENT-TYPE: %s
Content-Length: %d
Connection: close
```
with `CONTENT-TYPE` = `text/xml; charset="utf-8"` and body
`<?xml version="1.0" encoding="utf-8"?><s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>`

**The exact command, ready to run the moment 7676 is listening:**

```bash
CAM=192.168.107.1     # whatever the camera's address turns out to be

curl -v -X POST "http://$CAM:7676/smp_3_" \
  -H 'Content-Type: text/xml; charset="utf-8"' \
  -H 'User-Agent: SEC_RVF_ML_mac' \
  -H 'SOAPACTION: "urn:schemas-upnp-org:service:ContentDirectory:1#SetOperationState"' \
  --data-binary '<?xml version="1.0" encoding="utf-8"?><s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:SetOperationState xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1"><StateEvent>changeToRVF</StateEvent></u:SetOperationState></s:Body></s:Envelope>'

curl -o cam.ttts "http://$CAM:7679/livestream_high.avi"
```

The odd-looking `User-Agent` is deliberate. `UPnPControlDevice::GetDeviceNameForAcl` (@0x115dac)
derives the control-point identity from the User-Agent by **substring** match
(`SMPString::Find`) against registered filter patterns, and the pattern sitting in `.rodata` at
0x153af0 is `SEC_RVF_ML_` (immediately followed by a one-character reject-string `"\t"`).
Unmatched clients become `"unknown device N"` and are subject to the ACL mode, whose denial path
returns `401 UnAuthorised` / `503 ServiceUnavailable`. `[VERIFIED-EXTRACTED]`
**Caveat:** the call site that *installs* that filter rule was never located — no PC-relative
reference to 0x153af4 survives an ARM or Thumb xref scan, and the absolute pointer does not appear
anywhere in the file. So whether the ACL is even armed is `[UNKNOWN]`. Including the substring
costs nothing; if you get a 503, this is the first thing to suspect.

**(b) There are five streams, not one.** `[VERIFIED-EXTRACTED]`
`/livestream_high.avi`, `/livestream_middle.avi`, `/livestream_low.avi`,
`/livestream_recording.avi`, `/livestream_gearvr.avi`
(`libdi-network-dlna-rvf.so` @0x851fd, `libdi-network-dlna-dmsui.so` @0x106fe8). `GetInfomation`
returns them to the client as `<QualityHighUrl>`, `<QualityMiddelUrl>` (Samsung's spelling),
`<QualityLowUrl>`, `<QualityRecUrl>`, `<QualityGearVRUrl>`. The GearVR variant is advertised as a
fixed 2560×1280 at ratio 2:1.

**(c) The TTTS container is fully specified**, so the Mac side can be written *now*, before the
trigger problem is solved. `[VERIFIED-EXTRACTED]` The muxer is `cTTTWriter` in
`/usr/lib/libmmfcore.so` (`Src/AVMuxer/cTTTWriter.cpp`), all big-endian:

- **Header frame: 224 bytes**, tag sequence `TTTS`, `VID0` + per-stream `VD0<n>`, `AUD0` +
  per-stream `AU0<n>`, `ACC0`, `AC00`, `LIST`, `movi`. The 224 figure is the firmware's own log
  text (`"this is first packet but not a header frame (224 size) so drop this frame"`), which is
  authoritative; the field-by-field decomposition is `[INFERRED]` and only reproduces 224 if the
  innermost audio sub-record loop runs twice.
- **Every subsequent chunk:** 4-byte ASCII tag (`00VD` video, `00AU` audio), then `u32be size`,
  then `u64be timestamp` relative to the first frame, then payload.
- **On a video keyframe** the codec header (VPS/SPS/PPS) is prepended to the payload **and is
  counted in the size field.**
- Track ids: video = 1, audio = 2. The muxer drops any frame whose timestamp precedes the latched
  base.
- The 7679 responder validates that byte 0..3 of the first packet are `T`,`T`,`T`,`S` and drops
  the connection otherwise.
- Response headers are `Content-Type: video/x-avi`, `transferMode.dlna.org: Streaming`, and a
  `DLNA.ORG_PN=AVC_MP4_BL_CIF15_AAC_520` content-features line that is simply wrong for a 2560×1280
  HEVC stream — ignore it.

**Correction to prior community work:** the widely-circulated Android-app-derived reconstruction of
this container lists a `VRO0` tag where the firmware writes `ACC0`/`AC00`. A byte scan of all
11,567 rootfs files finds **zero** occurrences of `VRO0` or `00VR`. (`VROT`/`vrot` appear only in
`libmmfcore.so`'s MP4 writer, a different code path.) `[VERIFIED-EXTRACTED]` Trust the firmware.

Practical consequence: demuxing is trivial — skip 224 bytes, then loop {tag, size, ts, payload},
concatenate the `00VD` payloads, and you have an HEVC elementary stream ffmpeg will take directly.

#### What is still blocking a one-liner

`[VERIFIED-EXTRACTED]` **7676 does not exist until RVF is already running, and RVF is started only
by Bluetooth.** That is the chicken-and-egg, and it is now precisely located:

- In the phone-pairing Wi-Fi mode, **Bluetooth is what switches the Wi-Fi on**. No BT, no network,
  no 7676 to send the SOAP to.
- In Street View / OSC mode the camera brings Wi-Fi up entirely on its own — but that path is
  **code-disjoint** from RVF. OSC is served by `OSCDevice`/`ModeServer`/`OSCCnC` inside
  `libdi-network-dlna-api.so` (`./src/OSC/*`), and its command set is exactly
  `camera.{closeSession, delete, getImage, getMetadata, getOptions, listImages, setOptions,
  startSession, takePicture, updateSession}` — **there is no `camera.getLivePreview` and no video
  command of any kind.** This is a firmware-side fact that independently confirms the bench
  measurement that every live-preview spelling returns `unknownCommand`. It also explains why
  7676/7679 are closed in that mode: they belong to a subsystem that was never started.
- **None of the 33 `st app` verbs enters RVF.** `/usr/bin/st` (4,716 bytes, present) is a real live
  control channel into the running app — it sends System V messages via
  `ftok("/sem_app_res", 0x40)` → `msgget` → `msgsnd`, and `di-camera-app` imports
  `shell_app_set_start_function` / `start_shellthread` to receive them. The verb table
  (@0x4236c4, 33 entries) includes `wifidirect`, `softap`, `changemode`, `mode`, `net`. Their
  handlers were disassembled: `wifidirect start` → autonomous-GO only; `softap start` →
  `UI_SoftAP_Manager`; `changemode wifi` → launches `com.samsung.smart-wifi-app`; `mode wifi` →
  an `XTestFakeKeyEvent` keycode 223. **They bring Wi-Fi up. None of them calls
  `CUINETFuncDLNA::Start(RVF)`.** `[VERIFIED-EXTRACTED]` for the table's existence and contents;
  `[INFERRED]` for the per-handler disassembly (single-sourced).

**A lead I checked and am killing, so nobody wastes a day on it.** `di-camera-app` contains
`NETWORK_MAIN_REMOTE_VIEWFINDER`, `NW_START_REMOTE_VIEWFINDER`,
`WIDGET_ITEM_REMOTE_VIEWFINDER_MODE`, a whole `CAPPGUIRemoteViewfinderState` class, and
`14_remote_viewfinder_{nor,sel,dim}.png` icons — which looks exactly like an **on-camera menu item
that would start RVF with no phone at all.** It is not. `[VERIFIED-EXTRACTED]`
Two disqualifiers I verified myself:
1. The layout the code references, `/usr/apps/com.samsung.di-camera-app/res/edje/slp_edc_remote_viewfinder.edj`,
   **does not exist in the rootfs.** That directory contains exactly `images/`, `license.txt` and
   `tizen-hd.edj`.
2. The string sits in a table whose immediate neighbours are `NW_FACEBOOK`, `NW_PICASA`,
   `NW_DROPBOX`, `NW_KAKAOSTORY`, `NETWORK_MENU_HDMI_OUTPUT`, `NETWORK_MENU_ANYNET` — features
   this camera does not have. This is inherited NX-camera string data. (`/etc/parttab`'s first
   line is literally `# nx500 partition table`.)
   The class is entered on `onEventLiveview`, i.e. by the Bluetooth event, not by menu selection.

So: **string presence in `di-camera-app` is not evidence of a C200 feature.** This binary carries
a large amount of dead NX inheritance.

#### The two real routes, and what each still needs

| Route | Needs | Status |
|---|---|---|
| **A. Speak SAP from the Mac** — pair over Bluetooth, send `cmd-req`/`liveview`, camera brings up Wi-Fi, then the SOAP + GET above. | A working Samsung Accessory Protocol client. | JSON layer **fully recovered** `[VERIFIED-EXTRACTED]`. SAP **transport framing not recovered** — `[UNKNOWN]`. |
| **B. Root the camera, trigger internally** — SD-card script route to a root shell, then drive the app directly. | Root (obtainable with **zero block writes**), plus an injection method. | Root mechanism **verified present in this firmware** `[VERIFIED-EXTRACTED]`. Injection method **not yet built**. |

**On route A:** SAP is a TCP-like protocol layered on an RFCOMM socket, with session-ID
multiplexing, CRC-16 on data frames, and an authentication handshake exchanging hashes early in the
connection. It has been reverse-engineered publicly — javispedro's `sapd` (an experimental daemon
for Samsung Gear watches, at `git.javispedro.com/cgit/sapd.git`) is the closest existing base, and
the community's consistent report is that **the crypto/authentication portion is the hard part**
and was the piece missing from the circulated source drops. `[COMMUNITY]` — none of this was
verified against the C200, and whether the C200's `sap-server` demands the same authentication a
Gear 2 watch did is `[UNKNOWN]`. Note that the camera's own `libsap-api.so.1.0.0` is on disk and is
the authoritative spec for its half of the handshake, which is a meaningful advantage over the
people who reverse-engineered this from the phone side.

**On route B:** the injection point is identified. Bluetooth commands reach `di-camera-app` over
**D-Bus**, not through a private socket: `bt_le_manager` owns bus name `org.bt.app`, exposes
`app_service_request(iii,ay,ay,ay,ay,ay) -> (iv)` on `/org/bt/app_service`, and emits signals on
`org.bt.app_event` at `/org/bt/app_event`; `libdi-network-bt-app.so` registers for those events.
`[VERIFIED-EXTRACTED]` A root shell can emit on that bus. The exact argument encoding of a
`liveview` event is `[UNKNOWN]`. A cruder alternative also exists: `DlnaRVF_ML_FJ_Start` is an
**exported symbol** of `libdi-network-dlna-api.so`, so a tiny ARM binary could `dlopen`/call it —
though whether it works outside the app's own state machine is `[UNKNOWN]`.

**Root itself is verified reachable without writing a single block.** `[VERIFIED-EXTRACTED]`
`/usr/bin/dfmsd` has a script mode: its help text reads
`-c|--card [SCRIPT_FILE]  Launch daemon with script mode` … `NOTE: if script file isn't given, try
it with file given by /sdcard/info.tg`, it logs `script request: %s (cnt=%d)`, and its command
table (@0x17f218) contains a `shell` verb alongside the AT-command tag `+SHELLTST`. `/sdcard` is a
symlink to `/mnt/mmc` → `/opt/storage/sdcard` (verified in the extraction manifest), i.e. the SD
card. The archived trio from the stock updater confirms the format:
`info.tg` = `updater.adj`; `updater.adj` = `shell script /mnt/mmc/updater.sh`. `[VERIFIED-EXTRACTED]`

> **⚠ Do not copy those three files verbatim.** The stock `updater.sh` body is
> `mount -o bind /sdcard/ /opt/usr/media` + `/usr/sbin/fw_upgrade_start /sdcard/C200GLU0AQK1_….bin`
> — i.e. copying the archive.org set onto a card **performs a full firmware flash.** Write your own
> `updater.sh` that starts a shell or telnetd and touches no block device, and keep **zero**
> firmware-shaped files on that card. See §2 for why the filename rule is wider than you think.

---

# 2. Can we build and flash our own firmware?

## Verdict: **No.** And you do not need to.

Not "risky." Not "advanced users only." The build half is **hard-blocked by missing source**, and
the flash half has **no recovery path of any kind**. Both halves fail independently. Meanwhile
every goal in this project is reachable without flashing anything.

Taking the parts in order.

### 2.1 Is the image signed or verified? — No. And that is the *bad* news, not the good news.

`[VERIFIED-EXTRACTED]` + `[VERIFIED-SOURCE]` There is no RSA key, no ECDSA key, no certificate, no
signature block and no secure-boot logic anywhere in the boot chain. Scans of the bootloader
(partition 1), the Cortex-M4 image (partition 4), the T-Kernel (partition 5), and all three
`vmlinux` images for `-----BEGIN`, `BEGIN CERTIFICATE`, `secureboot`, and RSA SPKI DER prefixes
return **zero hits**. `emmc_bootloader/lib/` in the GPL source contains only `md5`, `crc` and `lzo`.
Grepping the released bootloader, `device-init`, `prefman`, `filesystem` and `initramfs` sources
for `verify_signature|rsa_verify|secure_boot|image_sign|fw_sign` returns **no matches**. The kernel
config has `# CONFIG_KEYS is not set`, `# CONFIG_IMA is not set`, `CONFIG_DEFAULT_SECURITY_DAC=y`,
no dm-verity and no module signing. (The 11 `BEGIN CERTIFICATE` hits in the raw image are the Tizen
TLS trust store under `/opt/etc/ssl/certs` plus `libcert-svc` — app-package signing, unrelated to
boot.)

**Read that correctly.** On a device with no recovery mode, the absence of validation is not
permission — it is the *brick mechanism*. Nothing will refuse a wrong image; it will simply be
written to eMMC.

### 2.2 Can we rebuild from the GPL source? — No. This is the hard blocker.

Two independent, verified reasons:

**(a) The image recipe was never released.** `[VERIFIED-SOURCE]` `sm-c200/Makefile` lines 142–145
symlink `tizen.ks`, `mic.conf`, `.gbs.conf` and `binary` from `$(PRODUCT_TOP)/project/…`. No
`PRODUCT_TOP` tree, no `tizen.ks`, no `mic.conf` and no `.gbs.conf` exists anywhere in either
release. `HOW_TO_BUILD.txt` documents only `make kernelconfig`, `make kernel`, `make vimage`,
`make device-init`, `make bootloader`, and `rpmbuild --rebuild` of individual SRPMs. **You can
rebuild the kernel, the bootloader, the M4 image and individual packages. You cannot produce the
shipped SLP `.bin`.**

**(b) The entire camera application is closed and absent.** `[VERIFIED-SOURCE]` This is the
decisive one, and it is specific to *this* project's goal. Everything that produces the stream —
`di-camera-app`, `libdi-network-dlna-{api,stack,rvf,dmsui,extlib,autobackup}`,
`libdi-network-bt-app`, `libmmfcore` (the TTTS muxer), `libmmfmodules` (the HEVC HAL),
`libcapture-fw-prod` — is proprietary and is **not in the GPL release at all.** The only
DRIMe5-specific multimedia source Samsung shipped is `gst-plugins-drime5-0.0.5`, whose entire code
directory is `drime5sink/` — a **display sink**. No encoder, no muxer, no streamer. Grepping the
whole source tree for `livestream|TTTS|7679|7676` returns nothing outside the RVF preference names.
There is no `gupnp` package either (only `gssdp`), so the UPnP device on 7676 is closed code too.

So "build our own firmware" would mean writing a 360 camera OS from scratch against an undocumented
proprietary SoC. That is not a project; that is a decade.

What you *could* do is **modify the extracted rootfs and repack** — a different and much more
dangerous thing, addressed next.

### 2.3 What does the updater actually check?

`[INFERRED]` — this is disassembly-derived from `fw_validate` @0x36e8 in
`/usr/lib/libfirmware-upgrade.so` and was **not** independently reproduced (a second pass desynced
on this library). Treat the mechanism as single-sourced; the *conclusion* is corroborated by the
independently-verified absence of any crypto.

1. `header[0..3] == "SLP\0"` — **or** `strncmp(header, "DRM5", 4) == 0`. `DRM5` is a live
   alternate magic (literal @0x90d0).
2. `num_image` at +0x2c must be 1..15.
3. Per slot: `magic == ((0xffffffff >> s) | (0x87654321 << s))`, `s = (i % 8) * 4`.
4. Per slot: **uncomplemented** CRC32, i.e. `~zlib.crc32(data)`, against the stored word.

That is all. `[VERIFIED-EXTRACTED]` I re-derived items 3 and 4 against the real file: all 10 slots
verify with the uncomplemented form (the standard final XOR-out mismatches every slot by exactly
0xffffffff), the sliding magic wraps at index 8 so slots 8/9 repeat slots 0/1, and the payloads
tile the file with zero gaps to byte 279,094,189 — exactly the file size, no trailer.

**Two corrections to earlier analysis:**

- **"Exactly four things" is wrong in both directions.** `[VERIFIED-EXTRACTED]` A hardware-version
  check *does* exist and is reachable: `fw_merge_check_hw` with the format string
  `required HW version : %s, Current HW version : %s` (@0x936c), plus `fw_get_bd_version`,
  `Body Boardversion : %s(%d)` (@0xa87c) and `F/W Snapshot Img. Boardversion: %s(%d)` (@0xa898).
  The symbol name appears inside `di-camera-app`, so it is not dead code. Whether it *aborts* is
  `[UNKNOWN]`. Conversely, the list under-counts what is **missing**: there is **no check of image
  size against partition size** anywhere, and **no check that the container's slot count or order
  matches the device's `/etc/imagetab`**.
- **Passing `fw_validate` proves nothing about flashability.** It confirms four self-consistent
  header fields. It does not check that slot 6 is really an lzo'd ext4, that it fits in the 1024 MB
  platform partition, or that slot 1 is a real bootloader. A hand-built container can be made to
  pass trivially.

**Is the model string enforced?** `[INFERRED]` Analysis found that `fw_validate`'s second argument
(the project name `"SMC200"`, read from `/etc/version.info`) is **dead** — r1 is clobbered five
instructions into the prologue, before being stored. I could not reproduce that disassembly, so the
specific mechanism is single-sourced. The *conclusion* is nonetheless well-supported: no
cryptographic model binding exists anywhere, `fw_upgrade` merely *prints* Project Name / Magic /
Version / Board Version and falls through with no comparison, and `fw_cmp_bl_version` /
`fw_cmp_ss_version` are referenced by nothing but the library defining them.

**The only model gate is a filename — and it is a glob, not a name.** `[VERIFIED-EXTRACTED]` I
extracted the vImage update kernel's own initramfs (12,715,520 bytes, 484 entries, gzip stream at
0x2cca94 of `part00_vmlinux`) and read the real update script. It accepts, via
`find … -maxdepth 1 -name`:

```
C200*        FTMA_C200*        smc200.bin        smc200_eng.bin
```

from `/mnt/mmc` — **or, if no card is inserted, from `/opt/usr/media` on internal storage.**

> **⚠ Practical rule.** Any file on the SD card whose name begins `C200` is a firmware candidate —
> including the stock `C200GLU0AQK1_171121_1257_REV00_user.bin`, or a half-copied `.part` file.
> And because the model string is genuinely unchecked, an NX500/NX1 image (same container, same
> lineage) would validate and flash. Never let more than zero firmware-shaped files sit on a card
> you insert.

### 2.4 What happens on failure? — There is no recovery. At all.

`[VERIFIED-SOURCE]` `check_recovery_condition()` in `emmc_bootloader/usr/Main.c:324` is
`{ // TODO : return 0; #if 0 … #endif }`. Its sole caller at line 1129 therefore **never** loads
`rImage`. The `#if 0` block reveals the intended key combo was
`SHUTTER_KEY2 + AEL_KEY + WIFI_KEY + FLIPUP_INT` — an NX-camera key set this body does not have.
`/usr/sbin/fw_upgrade_recovery` exists in the rootfs and can re-flash from `/dev/mmcblk1p1`, with
GUIs for "no fw" / "damaged fw" / "card err" — **and nothing in the released bootloader can reach
it.**

There is no download mode and no JTAG.

#### Correction — "reflash stock as an undo" is REFUTED

`[VERIFIED-EXTRACTED]` **The undo button is inside the room you would be setting on fire.** Every
firmware write on this device is performed by `fw_upgrade_start` called from *userspace* — from
`di-camera-app`'s UI, from `dfmsd`, or from the SD `updater.sh` — all of which live in the rootfs on
p9 and require a booting Tizen system. If a modified rootfs, a bad pref write or a stale snapshot
stops the system reaching `di-camera-app`, reflashing stock is simply not available.

And there is a second, unrecoverable asymmetry: **only one firmware binary exists anywhere on this
machine (AQK1). The owner's main unit runs C200GLU0APC9, for which we have source only — no `.bin`
— and every Samsung download host is dead.** `[VERIFIED-EXTRACTED]` for the local file inventory;
`[INFERRED]`/`[COMMUNITY]` for the hosts being dead. The APC9 unit has **no return path even in the
best case** and must not be written to under any circumstances.

### 2.5 The specific ways a first attempt bricks it

All `[INFERRED]` from disassembly of `/usr/sbin/fw_upgrade` unless marked otherwise; the
partition-table facts are `[VERIFIED-EXTRACTED]` (I read `/etc/imagetab` and `/etc/parttab`
directly).

**(a) Omitting or reordering a slot ERASES that partition.** This is the single most likely
first-try brick. `fw_get_image_num`, on a name not found in `/etc/imagetab`, writes `0xffffffff`
to its out-parameter and **returns success**. `fw_do_upgrade` then logs
`There is no image to flash.`, sets the image pointer to NULL, and **still calls the per-partition
handler** — which for a raw partition ≤ 100 MB runs `dd if=/dev/zero of=<dev> bs=1M count=<size>`
over the whole thing. Any custom container must carry **all 10 slots in exactly this order**:

```
vImage  bootloader.bin  uImage  rImage  devicem4.bin  rom.bin  rootfs.img  opt.img  pcache.list  snapshot.img
```

**(b) The blast radius is far wider than p9.** Every volume in `/etc/parttab` is processed on every
run — including `adj` p1 (20 MB), `pref` p2 (10 MB), `pref_default` p3 (30 MB), `pref_recovery` p4
(20 MB) and `rtos_data` p7 (50 MB), all of which have image `none`. Note that `pref_default.bin`
appears in `parttab` but **not** in `imagetab` — I verified this by reading both files — so it
resolves to index −1 and takes the NULL-image path.

**(c) The bootloader is written LAST.** `[VERIFIED-EXTRACTED]` `/etc/parttab` order column:
`bootloader /dev/mmcblk0boot0 … 15`, `uImage … 14`, `snapshot … 13`. The final act of every update
is a ~4 MB raw `dd` into the eMMC hardware boot partition, and `fw_set_boot_part_rw` deliberately
clears its `force_ro` protection first. Power loss in that window destroys the only code that runs
at reset. **Never start any flash on battery.**

**(d) Nothing checks size.** The write is `pv … | lzop -d -c | dd of=<partdev> bs=1M`. An oversized
rootfs writes until ENOSPC, leaving a truncated filesystem that passed CRC. Compression is taken
from the *device's* parttab (`lzo`), not from the container, so an uncompressed payload in slot 6
is fed to `lzop -d` and fails mid-write.

**(e) The stale-snapshot trap.** `[VERIFIED-SOURCE]` + `[VERIFIED-EXTRACTED]` This camera fast-boots
by resuming a hibernation image from p8. `is_snapshot_boot()` accepts it on a single 10-byte
`memcmp(SWSUSP_SIG, sw_hdr->sig, 10)`; `CONFIG_SNAPSHOT_CRC` is undefined and the shipped header's
crc32 field is literally `0x00000000`. `do_snapshot()` then `jump_to_resume()`s — **never reading
p9 or p5.** So a resumed kernel comes back holding the *old* rootfs's cached ext4 metadata on top
of your *new* disk, with `/` mounted read-only so nothing notices. The documented fix,
`/usr/bin/erase_snapshot.sh` (which I read: `dd if=/dev/zero of=/dev/mmcblk0p8 bs=1M count=80`,
`rm -rf /etc/snapshot`, `reboot -f`), **runs from the system it is repairing** — so it must be run
*before* touching the rootfs, in the same root session, or not at all.

**(f) A landmine for exactly this project.** `fw_emmc_flash_preproc` does `access("/sbin/parted",
F_OK)` and, **if parted exists**, runs `dd if=/dev/zero of=/dev/mmcblk0 bs=1M count=1`, then
`parted -s /dev/mmcblk0 mktable gpt`, then rebuilds every partition from parttab. I verified it is
dead today **only by packaging accident**: `find` over the rootfs returns no `parted`, and I parsed
all 484 cpio entries of the vImage initramfs — it ships `sbin/sfdisk`, `usr/sbin/gdisk`,
`usr/sbin/sgdisk`, `sbin/pv`, `bin/lzop`, `bin/dd`, `sbin/mke2fs` and **no parted** (the 15 raw
`parted` byte-hits are inside gdisk's own docs and man pages). `[VERIFIED-EXTRACTED]`
**Never ship `/sbin/parted` in a custom rootfs or initramfs.**

**(g) Backups that live only in RAM.** The real update script `dd`s three sector ranges of the pref
partition p2 into a 512 MB tmpfs and runs `restore_files.sh --backup` on `/opt/etc/bluetooth`,
`/opt/share/dfms`, `/opt/free_fall` and `/opt/usr/var/lib/bluetooth`. Power loss between the wipe
and the restore loses them permanently. `[VERIFIED-EXTRACTED]` (read from
`brick/vi_real_init.sh`).

### 2.6 Why the community never did it either

`[INFERRED]`, but well-grounded in the above. The Gear 360 modding scene stopped at exactly the
line these findings predict: people obtained **root** (via the `info.tg`/`.adj` script mechanism)
and changed **settings** (`st cap capdtm setusr`, bitrate tweaks) — and nobody shipped a custom
firmware image. That is not timidity. It is the rational response to: (i) the camera application is
closed and unbuildable, so there is nothing to *build*; (ii) the only flashing mechanism lives
inside the thing you would be replacing; (iii) there is no recovery mode, no download mode, no
JTAG, and a stubbed-out `check_recovery_condition()`; and (iv) the reward for succeeding is a
camera that does exactly what root already gives you. The cost/benefit never closed for them, and
it does not close here either.

### 2.7 One unresolved item that should be settled before any flash is ever contemplated

`[UNKNOWN]` Does a stock update really zero `/dev/mmcblk0p1` (`adj`, 20 MB, image `none`, order
1)? The NULL-image reading says yes. That would mean stock firmware updates destroy factory optical
calibration — which is implausible for a shipping product. The likely reconciliation is that p1 is
a *cache* of data `dfmsd` re-reads from a physical EEPROM (`dfms_set_adjdata`,
`EEPA_OPTICAL_AXIS_00..27`, and `rootfs/opt/share/dfms/dfms.log` contains real factory runs from
2016-03-18 writing exactly those keys). But it is unresolved. If the pessimistic reading is right,
a firmware update permanently degrades stitching — a *soft* brick nobody has accounted for.

---

# 3. Architecture — who owns which port and transport

`[VERIFIED-EXTRACTED]` throughout unless marked.

```
                              ┌──────────────────────────────────────────────┐
   Bluetooth RFCOMM           │      di-camera-app   (ONE process)           │
   SAP  /system/DI_360_2D     │                                              │
   uuid a49eb41e-…-aa80a90cdf4a                                              │
        │                     │  libdi-network-bt-app.so ──┐                 │
        ▼                     │                            ▼                 │
   sap-server ──► bt_le_manager ── D-Bus org.bt.app_event ──► CUINETFuncDLNA │
   (sap.service)   /org/bt/app_service                          │            │
                              │                                 ▼            │
                              │  libdi-network-dlna-api.so ─► DlnaRVF_ML_FJ_Start
                              │       │                          │           │
                              │       │                          ▼           │
                              │       │            libdi-network-dlna-rvf.so │
                              │       │              ├─ TCP 7676  UPnP/SOAP  │
                              │       │              │   /smp_3_ control     │
                              │       │              │   /smp_4_ eventSub    │
                              │       │              │   /smp_5_ SCPD        │
                              │       │              └─ TCP 9001  "http_ss"  │
                              │       │                  (separate server)   │
                              │       ├─ libdi-network-dlna-dmsui.so         │
                              │       │   └─ TCP 7679  RVFStreamingThruGet   │
                              │       │        /livestream_*.avi  (TTTS)     │
                              │       └─ ./src/OSC/*  ─ TCP 80  OSC/StreetView│
                              │  libmmfcore.so  cTTTWriter  (TTTS muxer)     │
                              │  libmmfmodules.so cHalHevcVideoEncoder       │
                              └──────────────────────────────────────────────┘
                                            │                    │
                          /dev/d5_hevc + /dev/d5_mptop      /dev/d5_sma + /dev/mem
                          (Cortex-M4 runs the codec,        (Cortex-A7 ISP delivers
                           enc_m4.bin)                        frames over IPCC)

   UDP/TCP 53  ──  dnsmasq, spawned by mobileap-agent for SoftAP.  NOT the camera app.
```

**Port detail**

| Port | Owner | Transport / notes |
|---|---|---|
| **7676** | `libdi-network-dlna-stack.so` (`HTTPTServer` / `UPnPControlDevice`) | Samsung "SMP" UPnP. Device desc + SOAP. Endpoints `/smp_3_` (ContentDirectory control), `/smp_4_`, `/smp_5_`; `/smp_6_`…`/smp_8_` ConnectionManager. SSDP 1900, event multicast 7900, UDP 24234, web 5215, UPnP 5216. |
| **7679** | `libdi-network-dlna-dmsui.so`, class `RVFStreamingThruGet` | HTTP GET of `/livestream_*.avi`, TTTS container. `HandleHeader` requires contentFeatures + `Host:`. |
| **9001** | `libdi-network-dlna-rvf.so`, **statically linked** `http_ss` server (`HttpSsCreate` / `AcceptThread`, started by `AT_HttpSeverStart`) | Entirely separate HTTP server. Port read from `HTTPPort` in `/mnt/mmc/.config/http_stream.ini`; defaults `HTTPPort=9001 CDSPort=5301 MaxConnections=32 StreamDir=DCIM/100PHOTO/`, written once and **never overwritten if the file exists**. Community nmap saw this as "tcpwrapped." |
| **80** | `libdi-network-dlna-api.so`, `OSCDevice`/`ModeServer`/`OSCCnC` | OSC/Street View. `/osc/info`, `/osc/state`, `/osc/checkForUpdates`, `/osc/commands/execute`, `/osc/commands/status`. Code path disjoint from RVF. The literal port constant was not recovered; **80 remains a bench observation.** |
| **53** | `dnsmasq` via `mobileap-agent` | SoftAP DHCP/DNS. |

**Wi-Fi bring-up.** SoftAP: Tizen `tethering_wifi_*` → `mobileap-agent` → `hostapd` on `wlan0`
with `max_num_sta=1`. The third IP octet is a **runtime variable** (`dhcp-range=192.168.` +
octet + `.3,…`), which is consistent with the observed 192.168.107.1 and rules out a hardcoded
subnet — `192.168.107.1` appears nowhere as a literal or as a u32. Wi-Fi Direct: `wifi_direct_*` →
`wfd-manager`/`p2p_supplicant` on `p2p-wlan0-0`, GO at 192.168.49.1, `udhcpd` pool .20–.40.
SoftAP is the **iOS fallback** (`UI_SoftAP_Creation_For_IOS`), and `CUINETDevSoftAP` has an explicit
`m_wait_softap_end` reservation so SoftAP is torn down before P2P starts.

**How the phone learns where to connect.** After the link is up the camera sends the UPnP
description URL back over Bluetooth as msgId `device-desc-url` (`SendBTMsgDlnaURL` →
`DlnaGetDeviceDescUrl`, built from `SMPGetNicList` + `HTTPTCPServerPort`). A hardcoded
`http://192.168.49.10:` literal sits in the same function's string block; the branch using it was
not decoded. `[INFERRED]`

**Bluetooth genuinely does nothing after Wi-Fi is up** — the teardown path explicitly
`pkill`s `bt_le_manager`, `bt-service`, `bt-core` and `bluetoothd`. This corroborates the bench
conclusion that BT's only job is switching Wi-Fi on.

**Config is data-driven and on the SD card.** Both `UPnPConfig.xml` and `http_stream.ini` live under
`/mnt/mmc/.config/` (with `/tmp/.config/` variants). `[INFERRED]` — the validator
(`_BinaryCheckFileData`) only appears to check for the `SHARED-MEDIA-FOLDER-PATH` line, so
hand-edited port values would likely survive; I read the strings, not the branch logic.

---

# 4. Non-RVF capture options

Short version: **there are none that bypass the camera application.** `[VERIFIED-EXTRACTED]`

- **No V4L2.** `drime5_nx360_defconfig` has `CONFIG_VIDEO_DEV=y` but
  `# CONFIG_VIDEO_CAPTURE_DRIVERS is not set` and `# CONFIG_V4L_MEM2MEM_DRIVERS is not set`. Every
  DRIMe5 media driver registers as a **misc** device (`misc_register`, `MISC_DYNAMIC_MINOR`) —
  `/dev/d5_hevc`, `/dev/d5_sma`, `/dev/d5_mptop`, `/dev/d5_ipcc`, not `/dev/video*`. The only
  `/dev/video*` strings in the whole image are **commented-out** lines in
  `/etc/rc.d/init.d/smack_default_labeling`. A root shell finds no `/dev/video` and no v4l2 ioctls.
- **The HEVC encoder is reachable only through one library.** `cHalHevcVideoEncoder` in
  `/usr/lib/libmmfmodules.so` opens `/dev/d5_hevc` and issues `D5_HEVC_ENCODE` (`_IOWR('t',8,…)`),
  driving the **Cortex-M4** via `/dev/d5_mptop` after loading `/usr/share/hevc/enc_m4.bin` (present,
  55,436 bytes). A full-rootfs byte scan finds `/dev/d5_hevc` in **exactly one** binary:
  `libmmfmodules.so`. Frames come from the **Cortex-A7 ISP** over `/dev/d5_sma` + `/dev/mem` +
  `libmulticore-bridge.so`. So "encode a frame" means reimplementing Samsung's multi-core protocol.
- **No gstreamer, no ffmpeg CLI.** Only a stale `gst-openmax.conf`. `libavcodec.so.54` etc. exist
  but are consumed solely by `libmmfile_formats.so` for file demux — a software path with no
  connection to the hardware encoder.
- **The UVC gadget is a dead end.** The kernel *does* build `f_uvc_slp` with a `uvc` function
  (`CONFIG_USB_G_SLP=y`), which looks tantalising. But
  `/usr/share/deviced/usb-configurations/usb-configurations.xml` offers only `mtp`, `acm+sdb` and
  `mass_storage` — **no `uvc` mode** — and there is **no uvc-gadget userspace daemon** anywhere in
  the image (`find -iname '*uvc*'` is empty). The runtime kernel even carries the string
  `Error There is no the_uvc!!`, confirming the pump must be supplied from userspace. Turning the
  camera into a USB webcam would mean writing that daemon **and** feeding it frames you can only
  get through the proprietary stack. `[VERIFIED-EXTRACTED]`
- **`dfmsd` is not a shortcut.** It is a factory/service daemon (EEPROM adjustment, ADC reads, OSD
  over IPCC, PTP). Its value here is the **script mode** (§1.4), not video. Amusingly it shipped
  with real factory logs still on board: `rootfs/opt/share/dfms/dfms.log` (94,819 B) has
  2016-03-18 runs writing `EEPA_OPTICAL_AXIS_00..27`, and `atd.log` (189,974 B) has a 2016-02-22
  AT-command session including `AT+WIFITEST`.

**How the dual fisheye is actually framed** — relevant because it determines what you get on the
wire. `[VERIFIED-EXTRACTED]` for dimensions; `[INFERRED]` for the compositing mechanism
(disassembly of `cMmfCamera::VideoCallback`, single-sourced). Two sensors (FRONT/REAR, each
1280×1280 for video) arrive as **separate, software-synchronised** frames — the code logs
`Left video` / `Right video` and `Skipping right video: Left video haven't arrived` — and are
composited into **one 2560×1280 side-by-side buffer** encoded by a **single** HEVC instance
(`HEVC[0] Cfg WH 2560x1280`). `CaptureImgType.h` labels this
`0:180, 1:360 without Stitching, 2:360 with Stitching`. **The live stream is mode 1: unstitched
side-by-side.** Real stitching (`CGPU_Stitch` / `libdi-arc-imagestitch`) is a separate stills/post
step and is not in the live encode path — so stitching must happen on the Mac. That is good news:
it is the same input the desktop Action Director expected.

**ABI, if anything ever needs cross-compiling.** `[VERIFIED-SOURCE]` + `[VERIFIED-EXTRACTED]`
ARMv7 **soft-float `gnueabi`, NOT armhf** — `e_flags 0x05000002` (both hard- and soft-float ABI
bits clear), interpreter `/lib/ld-linux.so.3`, eglibc 2.13, `libstdc++` max `GLIBCXX_3.4.16`,
VFPv3+NEON, kernel 3.5.0, 512 MB (`CONFIG_CMDLINE="console=ttyAMA0,115200n8 mem=512M@0xC0000000"`).
A **static musl armv7 soft-float** binary is the safest target. Getting the ABI wrong here is the
classic silent failure.

Two facts that make on-device work easier than expected: **SMACK is not compiled into the shipped
kernel** (`CONFIG_DEFAULT_SECURITY_DAC=y`, no `CONFIG_SECURITY_SMACK`, and the runtime `vmlinux`
contains **zero** `smack` strings despite the Tizen userland shipping smack tooling) — so root
faces no MAC barrier on any `/dev` node. And `/usr/sbin/sdbd` is present, so USB `sdb` is a second
route in. `[VERIFIED-EXTRACTED]`

---

# 5. Next concrete steps, ranked by value per risk

All bench work so far has been zero-risk. Steps 1–4 keep it that way — **nothing below writes a
block to either camera until step 5, and step 5 is a settings write, not a flash.**

Ground rule for everything: **the AQK1 unit is the guinea pig. The APC9 unit is not touched.**
There is no APC9 `.bin` anywhere and no way to obtain one.

### 1. Write the TTTS demuxer now. *(zero risk, high value, no camera needed)*
The container is fully specified in §1.4(c). Build and unit-test it against a synthetic file today.
When a stream is finally captured you want to be *watching video*, not debugging a parser at the one
moment the camera is cooperating. Deliverable: skip 224 bytes → loop {4-byte tag, u32be size, u64be
ts} → concatenate `00VD` payloads → feed ffmpeg as raw HEVC. Remember the keyframe VPS/SPS/PPS is
*inside* the size field.

### 2. Re-run the OSC-mode probe with the recovered SOAP. *(zero risk, decisive)*
Cheapest possible test of the most valuable hypothesis. Put the camera in Street View mode, join its
Wi-Fi, and fire the exact `curl` from §1.4 at 7676 anyway — plus a `GET /smp_5_` and a plain
`GET /` on 7676, and a connect attempt on **9001**, which nobody has probed. Expected result:
connection refused (matching the bench finding that only 53 and 80 are open). But it costs sixty
seconds and it definitively closes the question of whether the SOAP is reachable without Bluetooth.
Also worth confirming the exact ports with `nmap -p- ` rather than a short list.

### 3. Get root via the SD-card script route. *(low risk — zero block writes — very high value)*
This is the highest-value step in the list. `[VERIFIED-EXTRACTED]` mechanism, §1.4.
- Card with **exactly** `info.tg` + your `.adj` + your `.sh`. **No `C200*`, no `FTMA_C200*`, no
  `smc200*.bin`, no `.part` files.**
- Your script starts a shell/telnetd/sdbd and **touches no block device**. Do not reuse the
  archive.org `updater.sh` — its body is a flash command.
- First things to do with the shell, all read-only: `netstat -lntp` in each mode (settles the port
  ownership questions above), `cat /etc/version.info`, `st app` verb enumeration,
  `st cap capdtm usrlist` to **read and record** the current `USERDATA_WIFIMODE` value before
  anyone considers changing it.
- Then attempt the RVF trigger from inside: emit on `org.bt.app_event`, or call the exported
  `DlnaRVF_ML_FJ_Start`. If that works, the project is essentially done — you can script the whole
  thing over sdb/telnet.

### 4. Prove UART access on the AQK1 unit. *(low risk, but it is the precondition for everything else)*
`[VERIFIED-SOURCE]` The bootloader source has an unconditional UART entry — `Main.c:1021-1035`,
outside any `#ifdef`: Enter (0x0d) on UART0 within the first ~10 poll iterations calls
`do_bootloader_prompt()`, which supports `boot 0|1|2` (cold/snapshot/warm). `CONFIG_ENABLE_CONSOLE=y`.
**But the shipped defines target the `D5_ES` dev board and the real per-project config was never
released, so this is UNVERIFIED on retail silicon.** `[UNKNOWN]`
Find `ttyAMA0` pads, 115200 8N1. If you *can* get a prompt, you have a rescue for a bad kernel or
rootfs. If you *cannot*, then every write to eMMC is irreversible by design — which is itself the
most important thing to know, and it should be known **before** step 5, not after.

### 5. Only then, and only on AQK1: the `USERDATA_WIFIMODE` experiment. *(medium risk — first step that persists)*
`[COMMUNITY]` `ottokiksmaler/gear360_modding` documents
`st cap capdtm setusr 84 0x540001` (`USERDATA_WIFIMODE` = `WIFIMODE_RVF`). It is **not corroborated
by anything in the extracted firmware** and nobody has tested it. Supporting context that makes it
plausible: `[VERIFIED-SOURCE]` `mm_camera_data_type.h` defines `MM_CAMERA_WIFIMODE_RVF` as the
**only** Wi-Fi mode the camera firmware knows, alongside `INVALID`/`OFF`/`MAX`.
**Why it is medium and not low risk:** this is a **persistent write into the pref partition**
(`/dev/mmcblk0p2`), pref CRC checking is **compiled out** (`//#define PREF_CRC_CHECK`), there is no
on-device validation of what you write there, and no user-visible factory reset is proven to reach
it. Read and record the current value first. Prefer any runtime/volatile route over a pref write.

### 6. The Bluetooth SAP client. *(zero hardware risk, highest effort, the real prize)*
If step 3 succeeds this becomes optional; if step 3 fails this is the only remaining path. The JSON
layer is done (§1.2). The work is the SAP transport: RFCOMM socket, session multiplexing, CRC-16,
and an authentication handshake. `[COMMUNITY]` javispedro's `sapd`
(`git.javispedro.com/cgit/sapd.git`) is the closest existing base and the auth/crypto is the
known-hard part. **Your advantage over everyone who tried before:** you have the camera's own
`libsap-api.so.1.0.0` on disk, which is the authoritative implementation of the peer's half. Start
by disassembling its handshake rather than by porting someone else's phone-side guess.

### Not on this list, deliberately
Building or flashing custom firmware. See §2. It is blocked, it is unrecoverable, and — decisively
— **every objective above is achievable without it.**

---

# 6. What we could not determine

`[UNKNOWN]`, all of it. This section is as important as the findings.

1. **The SAP transport framing.** The JSON is fully recovered; the bytes that carry it are not. This
   is the single gap between "we understand the camera" and "we can drive it phone-free."
2. **The exact D-Bus argument encoding** of an `org.bt.app_event` `liveview` event — the injection
   point is identified, the payload is not.
3. **Whether 7679 binds at DLNA-start or at `changeToRVF`**, and whether the encoder is idle until
   the client GET. `StartHTTPServer` is reached via `StartRVFDevice`, which both `DlnaRVFStart` and
   `DlnaRVF_ML_FJ_Start` call, but the gating by the closed `CDSRVF_Sysfunc_SetOperationState` layer
   was not resolved. **The earlier claim that "the GET starts the encoder" is retracted** (§1.3).
4. **Whether the ACL is armed.** The `SEC_RVF_ML_` pattern is in `.rodata` but **no call site
   installs it** — capstone ARM and Thumb xref scans for references to 0x153af4 return nothing, and
   the absolute pointer appears nowhere in the file. So the User-Agent may not matter at all.
5. **Whether the retail bootloader has the UART prompt.** Source says unconditional; shipped
   defines target the ES dev board; the retail blob proves nothing either way. Must be tested.
6. **Whether `fw_merge_check_hw` actually aborts** on a board-version mismatch, or only logs. This
   matters because AQK1 and APC9 may not be board-compatible.
7. **Whether a stock update really zeroes the `adj` partition p1**, and if so whether optical-axis
   calibration is recoverable from a physical EEPROM. §2.7. Potential silent, permanent quality loss.
8. **Which image index stage 1 writes into the p5 slot.** `parttab` says `uImage` (index 2); the
   error string says `vImage`. `parttab` has no `vImage` volume at all. Circumstantial evidence
   favours a substitution, but the selection logic was not decoded.
9. **The OSC port constant.** 80 is a bench observation; the literal was never found in
   `libdi-network-dlna-api.so`.
10. **The SoftAP third octet.** Chosen at runtime; `192.168.107.1` appears nowhere as a literal or
    as a u32 (`c0a86b01`/`016ba8c0`). The selecting code was not found.
11. **Verification limits, stated plainly.** An adversarial pass re-confirmed every cited symbol
    address and adjacent string literal, but **could not reproduce the ARM/Thumb call edges** — its
    disassembler desynced (717 BLs decoded, 1 landing in a 961-entry PLT). So the RVF call graph,
    the `fw_validate` dead-argument proof, the `fw_get_image_num` erase-on-missing behaviour, the
    `st` handler analysis and the dual-fisheye compositing are **strong but single-sourced**.
12. **Download-side claims not re-executed.** The availability of the APC9 source split-zip on XDA
    and Samsung's delisting of SM-C200 from `opensource.samsung.com` were established by one agent's
    network fetches and were not independently repeated. The **only** download-side fact
    independently confirmed is that the local firmware's SHA256 matches the archived Samsung
    manifest — the image is authentic and uncorrupted.

---

# 7. Corrections — where verification overturned an analysis claim

| Claim as originally stated | Status | Corrected statement |
|---|---|---|
| "The HTTP GET itself starts the encoder." | **Overstated** | The GET handler *contains* a path to `start_RVF_streaming`. 7679 is already listening before any GET, so the bind is not caused by the GET; encoder-idle-until-GET is unproven. |
| "The update path validates exactly four things." | **Overstated (both ways)** | A reachable HW-version check (`fw_merge_check_hw`) also exists. And the list omits what is *missing*: no image-size-vs-partition-size check, no slot-count/order check against `imagetab`. |
| "Reflashing stock is a safe undo." | **Refuted** | The only flash mechanism lives in the rootfs being modified and needs a booting Tizen system. No recovery mode, no download mode, no JTAG. And no APC9 binary exists at all. |
| "The stock update path cannot repartition the eMMC." | **Refuted** | `fw_emmc_flash_preproc` will `mktable gpt` and rebuild every partition **if `/sbin/parted` exists**. Dead today only because parted is not packaged — verified across the rootfs and all 484 initramfs entries. |
| "The only model gate is the filename `smc200.bin`." | **Too narrow** | It is a glob: `C200*`, `FTMA_C200*`, `smc200.bin`, `smc200_eng.bin`, from the SD card **or** from `/opt/usr/media` when no card is present. |
| "Mapping is positional against `/etc/imagetab`" (stated neutrally) | **Incomplete — the dangerous half was missing** | On a name not found, `fw_get_image_num` returns **success** with index −1, and the caller then **erases** that partition rather than skipping it. |
| Community/Android-app reconstruction lists a `VRO0` TTTS tag. | **Refuted** | The firmware writes `ACC0`/`AC00`. Zero occurrences of `VRO0`/`00VR` in all 11,567 rootfs files. |
| Prior-art nmap labelled 7676 "Samsung AllShare httpd". | **Imprecise** | That is a banner guess. The release ships `gssdp` but **no `gupnp`** — the UPnP device is closed Samsung code. |
| GearVR `<Width>2560</Width>…` quoted as one contiguous literal. | **Minor** | It is assembled at runtime from adjacent format fragments. Substance unaffected. |
| `NETWORK_MAIN_REMOTE_VIEWFINDER` / RVF menu strings suggest an on-camera RVF menu. | **Refuted (found in this pass)** | The referenced `slp_edc_remote_viewfinder.edj` **is not in the rootfs**, and the string sits among `NW_FACEBOOK`/`NW_PICASA`/`NETWORK_MENU_HDMI_OUTPUT` — dead NX inheritance. `/etc/parttab` literally begins `# nx500 partition table`. |
| BT command vocabulary is 17 commands. | **Undercounted (found in this pass)** | The `.rodata` table also contains `bt-off`, `timer`, `timer stop`, `timer end`, `capture`, `capture end`, `record`, `record end`, `disconn`, `get`, `set`, `single`. Note `reset_device` uses an underscore where siblings use hyphens. |

---

# Appendix — artifacts and how the image decomposes

**Source file, unmodified:** `/Users/zifan/Dev/claude/gear360-c200/firmware/C200GLU0AQK1.bin`
SHA256 `150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db` — re-verified at the end
of this work. All operations were performed on a copy.

**Container.** SLP **V2**: 64-byte `fwfile_meta` at 0x00, ten 24-byte `fw_image_header` records at
0x40–0x12F (`{u32 size, u32 crc32, u32 offset, u32 magic, char[8] tag}`), then ten payloads with
**zero gaps and no trailer**, ending at byte 279,094,189 = the file size exactly.
All 10 CRC32s and all 10 sliding magics verify. `[VERIFIED-EXTRACTED]`

Header fields: `SLP\0` @0x00; `0.85` @0x04 — this is **`Firmware Version(USER)`, not the container
format version**; `SMC200` @0x0c; `SMC200GLU0AQK1` @0x1c; `num_image=10` @0x2c; snapshot-included
flag @0x30; `VER_Rev0.6` @0x31. All five match `/etc/version.info` line for line.

| # | Offset | Size | Identity | Target (`/etc/imagetab` → `/etc/parttab`) |
|---|---|---|---|---|
| 0 | 0x00000130 | 6,532,944 | uImage → zImage, `Linux-3.5.0` #22 2017-05-19, **carries a 483-entry cpio initramfs** (the update stage) | `vImage` → p5 |
| 1 | 0x0063b080 | 52,793 | DRIMe5 bootloader, tag `08E6824` | `bootloader.bin` → `mmcblk0boot0`, order **15 (last)** |
| 2 | 0x00647eb9 | 3,880,960 | uImage, `Linux-3.5.0` #5 2017-09-15 — the kernel the snapshot was taken on | `uImage` → p5, order 14 |
| 3 | 0x009fb6b9 | 6,765,536 | uImage, `Linux-3.5.0` #521 2016-02-01, carries a cpio | `rImage` → p12 (**unreachable**) |
| 4 | 0x0106f299 | 125,292 | Cortex-M4 image; SP 0x000219c8, Thumb vectors, `SYS_M4DEV`, `[CM4] Unexpected HardFault` | `devicem4.bin` → `mmcblk0boot1` |
| 5 | 0x0108dc05 | 9,905,408 | T-Kernel 2.01.03 / T-Monitor `_D5_CA7_` 2.01.00 (Cortex-A7 RTOS) | `rom.bin` → p6 |
| 6 | 0x01a00105 | 196,357,034 | lzop → **372,195,328 B ext4 `rootfs`** | `rootfs.img` → p9 |
| 7 | 0x0d546f69 | 5,193,272 | lzop → 104,857,600 B ext4 `opt` | `opt.img` → p10 |
| 8 | 0x0da3c08b | 20,480 | `PAGECACHELIST` — 282 preload paths incl. `/usr/lib/libdi-network-dlna-rvf.so` | `pcache.list` → p11 |
| 9 | 0x0da4108b | 50,232,056 | lzop → 128 MiB swap containing an `S1SUSPEND` **hibernation image** | `snapshot.img` → p8 |

Rootfs is **Tizen 2.2.0 "Magnolia"**, `/etc/info.ini`: `Model=SMC200; Build=C200GLU0AQK1;
Date=2017.11.21; Time=12:59:33`. The ext4 superblock's `s_last_mounted` is
`/home/dpi/qb5_8814/workspace/NX360/D5/build/rootfs` — the NX lineage, in Samsung's own words.
Exactly **one** real embedded filesystem exists in the whole image and it is invisible until the
rootfs is decompressed: a squashfs 4.0 (LZO, 484 inodes, 17,725,501 B) at offset 0x0ca99000 of the
decompressed rootfs.

**Working artifacts** (all under
`/private/tmp/claude-501/-Users-zifan/56d29e7e-0800-4514-a995-15f51e798321/scratchpad/`):

| Path | What |
|---|---|
| `fw/rootfs/` | Extracted root filesystem, `/opt` merged in as it mounts on the device. 1,143 dirs, 11,567 files, 869 symlinks, 330 MB, 1,659 ELFs, **0 truncated**. |
| `fw/rootfs_case_collisions/` | 21 files in 13 groups that cannot coexist on case-insensitive APFS (`libxt_MARK.so` vs `libxt_mark.so`, `terminfo/E/Eterm` vs `e/eterm`), re-extracted byte-exact. None streaming-related. |
| `fw/rootfs_manifest.json` | Full manifest incl. the 12 device nodes (major/minor recorded; not `mknod`'d — needs root). |
| `fw/sections/` | The 10 raw partitions. |
| `fw/kernels/` | Three decompressed `vmlinux` images (gzip piggy at a constant +0x5580 into each zImage body). |
| `fw/str/rvf_xml.txt` | 64,004 B — the complete reconstructed RVF device description + 50-action ContentDirectory SCPD. |
| `brick/vimage_initramfs.cpio`, `brick/vi_real_init.sh` | The update kernel's initramfs and the real update script. |
| `fw/aqk1/`, `fw/apc9/` | Samsung GPL source, both builds. **APC9 ships kernel + exfat only** — no bootloader, no M4, no initramfs. AQK1 is the more complete release. |
| `fw/slp_parse.py`, `fw/lzop_unpack.py`, `fw/myext4.py` | The from-spec container parser, lzop (LZO1X) reader, and custom ext4 extractor. |

**Tooling notes for anyone repeating this.** `python-lzo` will not build here (bundled liblzo2 fails
under clang); the `lzallright` wheel installs cleanly and provides LZO1X. The PyPI `ext4` package
**mis-parses these images** (`OpenDirectoryError: Unexpected file type: 211` on the rootfs root
inode) — hence the custom reader. No binwalk, 7z or unsquashfs was needed or used.

**Two caveats for anyone mounting the images.** Partition 7's ext4 does **not** fill its slot —
declared size is 77,160,448 B but the blob is 104,857,600 B, with live-looking content past the
declared end — and its journal is **dirty** (`s_feature_incompat=0x246`, the extra 0x004 being
`NEEDS_RECOVERY`). Mount read-only and treat anything past 0x04996000 as salvage, not filesystem.
