# C200 firmware — verification data

**No firmware binary is committed to this repository.** Samsung firmware is
copyrighted and is not redistributed here. What is published is the information
needed to verify a copy you obtained yourself.

Every original Samsung download host for this model is now dead (NXDOMAIN). If
you hold a verified copy, keep at least two offline backups. `[VERIFIED]`

---

## ⚠️ This image is the GLOBAL build. Check your unit's region first.

`[VERIFIED]` `C200GLU0AQK1.bin` contains exactly one C200 build string,
`SMC200GLU0AQK1` — the **GLU (global)** build. `[VERIFIED]` Samsung China lists
this camera as model **`SM-C200NZWACHN`**, so at least one regional variant
exists that this image does not correspond to.

**`[UNKNOWN]` Whether the GLU image is safe to flash to a non-GLU unit. Nobody
has published an attempt.** Cross-*model* flashing (R210 → C200) is a documented
unrecoverable brick; cross-*region* flashing of the same model is usually benign
on Samsung phones, but **that experience has never been validated on this
camera** and it must not be assumed here.

**Practical consequence:** if your unit is not a GLU unit, **this image is not
your recovery image**, and the safety argument that "a verified recovery image
makes the risk manageable" does not apply to you. Establish your region code
before relying on it.

**How to check:** the full model code is printed on the camera body / in the
battery compartment, in the form `SM-C200NZWA` + a three-letter region code.

### The region hypothesis was tested and REFUTED `[VERIFIED on hardware, 2026-07-27]`

A mainland-China-market unit with a memory card inserted shows **no
`Google Street View` entry** in the press-and-hold menu, while the global launch
manual (English, 05/2016, Rev.1.0) documents it. The obvious explanation was a
China-specific firmware with Google integrations removed.

**That explanation is wrong.** EXIF from a photo taken on that unit reports
`Software = C200GLU0AQK1` — the camera is running the **global** build, and
specifically the **final** one. So:

- Flashing the global image to that unit would be a **no-op**, not a fix.
- The missing menu entry is **not** a regional difference.
- `[INFERRED]` The remaining explanation is that the entry was **removed in a
  later firmware build**. The launch manual documents it at 05/2016; it is absent
  on `AQK1` (2017-11-21, the last build). Untested against an earlier build —
  **if you have a C200 on `APC9`/`APE4`/`API1`/`AQC1`/`AQF1`, please report
  whether `Google Street View` appears in your press-and-hold menu.** That single
  observation would settle it.

**Note for `AQK1` owners:** `[COMMUNITY]` there are directly contradictory
reports about whether this final build breaks the remote viewfinder, and every
wire-level live-stream capture in this repository comes from `APE4`, the
*oldest* build. If you own two units on different builds, **do not update the
older one** — on this project's main line it is the more valuable of the two.

---

## `C200GLU0AQK1` — final SM-C200 build

Distributed as `C200GLU0AQK1_171121_1257_REV00_user.bin` (some mirrors shorten
the name; the bytes are what matter).

| Property | Value |
|---|---|
| SHA256 | `150bc48362555a4812e8871ff581c693f50f80e3e31e4647d2b563e9072c48db` |
| Size (bytes) | `279094189` |
| SLP magic | `SLP\0` at offset `0x00` |
| Format version | `0.85` at offset `0x04` |
| Project | `SMC200` at offset `0x0C` |
| Build | `SMC200GLU0AQK1` at offset `0x18` |

Verify before the file goes anywhere near a camera:

```bash
shasum -a 256 C200GLU0AQK1*.bin
stat -f %z    C200GLU0AQK1*.bin     # macOS;  stat -c %s  on Linux
xxd -l 48     C200GLU0AQK1*.bin
```

Expected hexdump of the first 48 bytes:

```
00000000: 534c 5000 302e 3835 0000 0000 534d 4332  SLP.0.85....SMC2
00000010: 3030 0000 0000 0000 0000 0000 534d 4332  00..........SMC2
00000020: 3030 474c 5530 4151 4b31 0000 0a00 0000  00GLU0AQK1......
```

## The five-second model check

`[VERIFIED]` The string `SMR210` occurs **zero** times in the entire 279 MB
C200 image. The project name sits in plaintext at offset `0x0C`.

```bash
strings -n 6 FIRMWARE.bin | grep -m5 -E 'SMC200|SMR210'
```

**If you see `SMR210` anywhere, that image is for the 2017 camera. Do not flash
it to a C200.** `[COMMUNITY, strongest evidence in the corpus]` Cross-flashing
R210 firmware onto a C200 is the documented hard-brick path and **no camera
bricked this way has ever been recovered.** See
[`../03-safety-and-recovery.md`](../03-safety-and-recovery.md) §1.1.

`[UNKNOWN]` Whether the camera's own `fw_upgrade_start` validates this header
before writing. **Do not rely on the camera to catch the mistake — check it
yourself.**

## Other builds

`[COMMUNITY]` Reported C200 builds, oldest to newest:
`C200GLU0APC9`, `APE4`, `API1`, `AQC1`, `AQF1`, `AQK1`.

All wire-level live-stream evidence in this repository comes from **APE4**, the
oldest build. `[COMMUNITY]` There are directly contradictory reports about
whether the final `AQK1` build breaks the remote viewfinder. Hashes for builds
other than `AQK1` are **not** established here — if you have one, a verified
hash is a welcome contribution.
