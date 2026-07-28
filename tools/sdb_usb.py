#!/usr/bin/env python3
"""Minimal sdb-over-USB client for the SM-C200 -- no Tizen Studio needed.

The Gear 360 (Tizen) exposes the Samsung Debug Bridge over USB when the gadget
is in a mode that includes the `sdb` function (04e8:6860, acm+sdb). sdb speaks
the same wire protocol as adb, and the camera's `sdbd` runs in rootshell mode,
so no RSA auth is needed -- this gives a root shell.

macOS binds no driver to the sdb interface (vendor class 0xff), so libusb can
claim it directly. Requires: pyusb + libusb (both already present here).

Usage:
    python3 sdb_usb.py                 # interactive root shell
    python3 sdb_usb.py "id; uname -a"  # run one command, print output, exit
    python3 sdb_usb.py --probe         # just show the device/interface layout

The wire protocol (adb/sdb): 24-byte header of 6 little-endian u32
    command, arg0, arg1, data_len, data_crc32, magic(=command ^ 0xffffffff)
followed by data_len payload bytes. Commands: CNXN OPEN OKAY WRTE CLSE AUTH.
"""

from __future__ import annotations

import struct
import sys
import threading
import time

import usb.core
import usb.util

VID, PID = 0x04E8, 0x6860

A_CNXN = 0x4E584E43
A_OPEN = 0x4E45504F
A_OKAY = 0x59414B4F
A_WRTE = 0x45545257
A_CLSE = 0x45534C43
A_AUTH = 0x48545541

VERSION = 0x01000000
MAXDATA = 256 * 1024


def _find_sdb_interface(dev):
    """Return (interface, ep_out, ep_in) for the sdb function.

    sdb is a vendor-specific interface (class 0xff) with one bulk-IN and one
    bulk-OUT endpoint. The ACM data interface is also class 0xff-ish on some
    stacks, so prefer subclass/protocol 0x42/0x01 (adb/sdb) when present, else
    the first vendor interface with a bulk pair.
    """
    cfg = dev.get_active_configuration()
    candidates = []
    for intf in cfg:
        bulk_in = bulk_out = None
        for ep in intf:
            is_bulk = usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            if not is_bulk:
                continue
            if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                bulk_in = ep.bEndpointAddress
            else:
                bulk_out = ep.bEndpointAddress
        if bulk_in is not None and bulk_out is not None:
            score = 0
            if intf.bInterfaceClass == 0xFF:
                score += 1
            if (intf.bInterfaceSubClass, intf.bInterfaceProtocol) == (0x42, 0x01):
                score += 10  # canonical adb/sdb
            candidates.append((score, intf, bulk_out, bulk_in))
    if not candidates:
        return None, None, None
    candidates.sort(key=lambda t: -t[0])
    _, intf, epo, epi = candidates[0]
    return intf, epo, epi


class SdbUsb:
    def __init__(self, dev, epo, epi):
        self.dev, self.epo, self.epi = dev, epo, epi
        self._lock = threading.Lock()

    def _send(self, cmd, a0, a1, data=b""):
        if isinstance(data, str):
            data = data.encode()
        crc = sum(data) & 0xFFFFFFFF
        hdr = struct.pack("<6I", cmd, a0, a1, len(data), crc, cmd ^ 0xFFFFFFFF)
        with self._lock:
            self.dev.write(self.epo, hdr, timeout=5000)
            if data:
                self.dev.write(self.epo, data, timeout=5000)

    def _recv(self, timeout=5000):
        hdr = self.dev.read(self.epi, 24, timeout=timeout)
        cmd, a0, a1, dlen, crc, magic = struct.unpack("<6I", bytes(hdr))
        data = b""
        while len(data) < dlen:
            chunk = self.dev.read(self.epi, min(dlen - len(data), MAXDATA), timeout=timeout)
            data += bytes(chunk)
        return cmd, a0, a1, data

    def connect(self):
        self._send(A_CNXN, VERSION, MAXDATA, b"host::\x00")
        for _ in range(6):
            cmd, a0, a1, data = self._recv()
            if cmd == A_CNXN:
                return data.decode("latin-1", "replace")
            if cmd == A_AUTH:
                # Rootshell sdbd usually does not require auth. If it does, we
                # cannot sign without the private key; report it.
                raise RuntimeError("device requires AUTH (RSA) -- rootshell not enabled")
        raise RuntimeError("no CNXN response")

    def shell(self, command: str | None):
        """Open shell: (command) runs one command; None = interactive."""
        local_id = 1
        service = "shell:" + (command if command else "") + "\x00"
        self._send(A_OPEN, local_id, 0, service.encode())
        cmd, remote_id, a1, _ = self._recv()
        if cmd == A_CLSE:
            raise RuntimeError("device refused shell service")
        if cmd != A_OKAY:
            raise RuntimeError("unexpected reply to OPEN: %08x" % cmd)
        remote_id = a1 if a1 else remote_id

        stop = threading.Event()

        def pump_out():
            # device -> us
            while not stop.is_set():
                try:
                    c, a0, a1, data = self._recv(timeout=1000)
                except usb.core.USBError:
                    continue
                if c == A_WRTE:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                    self._send(A_OKAY, local_id, a0)
                elif c == A_CLSE:
                    self._send(A_CLSE, local_id, a0)
                    stop.set()
                    return

        t = threading.Thread(target=pump_out, daemon=True)
        t.start()

        if command is not None:
            t.join()  # one-shot: wait for CLSE
            return

        # interactive: us -> device
        try:
            while not stop.is_set():
                line = sys.stdin.readline()
                if not line:
                    break
                self._send(A_WRTE, local_id, remote_id, line.encode())
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            try:
                self._send(A_CLSE, local_id, remote_id)
            except Exception:
                pass


def main(argv):
    probe_only = "--probe" in argv
    args = [a for a in argv if not a.startswith("--")]
    command = args[0] if args else None

    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print("device 04e8:6860 not found. Is the camera in acm,sdb USB mode?",
              file=sys.stderr)
        return 2

    intf, epo, epi = _find_sdb_interface(dev)
    if probe_only or intf is None:
        cfg = dev.get_active_configuration()
        for i in cfg:
            eps = [(hex(e.bEndpointAddress),
                    usb.util.endpoint_type(e.bmAttributes)) for e in i]
            print(f"interface {i.bInterfaceNumber} "
                  f"class={i.bInterfaceClass}/{i.bInterfaceSubClass}/{i.bInterfaceProtocol} "
                  f"eps={eps}")
        if intf is None:
            print("\nNo bulk-pair (sdb) interface found. The gadget is probably "
                  "still in MTP/PTP mode, not acm,sdb.", file=sys.stderr)
            return 3
        print(f"\nsdb interface = {intf.bInterfaceNumber}, out={hex(epo)}, in={hex(epi)}")
        if probe_only:
            return 0

    try:
        if dev.is_kernel_driver_active(intf.bInterfaceNumber):
            dev.detach_kernel_driver(intf.bInterfaceNumber)
    except (NotImplementedError, usb.core.USBError):
        pass
    usb.util.claim_interface(dev, intf.bInterfaceNumber)

    client = SdbUsb(dev, epo, epi)
    banner = client.connect()
    print(f"[connected] {banner.strip()}", file=sys.stderr)
    client.shell(command)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
