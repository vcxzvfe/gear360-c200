# Card files — Stage-A reconnaissance

These three files, written to the **root of a FAT32 microSD card**, drive an SM-C200 into
`dfmsd` script mode and run a read-only reconnaissance pass whose output lands back on the
card. Full procedure and safety rationale: [`../../09-root-procedure.md`](../../09-root-procedure.md).

## What goes on the card

| Card file | Source | Exact contents |
|---|---|---|
| `info.tg` | write by hand | `recon.adj` + one newline |
| `recon.adj` | write by hand | `shell script /mnt/mmc/recon.sh` + one newline |
| `recon.sh` | copy [`recon.sh`](recon.sh) | the read-only recon script |

Create the two tiny files with LF line endings and a single trailing newline:

```bash
printf 'recon.adj\n'                       > /Volumes/YOUR_CARD/info.tg
printf 'shell script /mnt/mmc/recon.sh\n'  > /Volumes/YOUR_CARD/recon.adj
cp tools/card/recon.sh                       /Volumes/YOUR_CARD/recon.sh
```

## Safety — verify before inserting the card

- [ ] Card is FAT32.
- [ ] **No file on the card begins with `C200`.** No `.bin`. No `.part`. (Any of these
      would be treated as firmware and flashed — the model string is not checked.)
- [ ] `recon.sh` is the unmodified read-only script — no `dd`, `mount`, `fw_upgrade`, or
      write to `/dev/mmcblk*` anywhere in it.
- [ ] This card goes in the **AQK1** unit only. The APC9 unit has no recovery image and is
      not part of this.

## After it runs

Power off, move the card to the Mac, and read `recon-out/`. `recon-out/DONE` present means
the script finished. If it is absent, the chain did not fire — re-check that `info.tg` and
`recon.adj` are byte-exact (one trailing `\n`, no trailing space, LF not CRLF) before
anything else.

Send the whole `recon-out/` folder back and the next step is chosen from real evidence:
which process owns the ports, whether `/dev/video*` exists, whether `sdbd` opened a TCP port,
and the D-Bus surface for triggering RVF from inside.

## Reversal

Delete `info.tg` from the card. Nothing was written to the camera; Stage A leaves no
persistent change on the device.
