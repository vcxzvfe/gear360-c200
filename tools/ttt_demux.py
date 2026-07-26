#!/usr/bin/env python3
"""
Gear 360 (SM-C200 / SM-R210) RVF live-stream demuxer.

Connects to the camera's RVF HTTP streaming port (7679) and writes the raw
HEVC (H.265) Annex-B elementary stream to stdout, so it can be piped into
ffmpeg / ffplay / OBS.

    python3 ttt_demux.py http://192.168.107.1:7679/livestream_high.avi \
        | ffplay -fflags nobuffer -flags low_delay -f hevc -i -

STATUS: UNTESTED against real hardware. The wire format below is transcribed
from the only two independent implementations that exist, both of which target
this exact camera family:
  * TecCheck/Gear360App  app/src/main/java/io/github/teccheck/gear360app/live/MediaExtractor.java
  * TecCheck/Gear360App  app/src/main/java/io/github/teccheck/gear360app/player/Extractor.kt
and cross-checked against a real SM-C200 device log (ultramango/gear360reveng
logfiles/..._a9_dlog.info) which shows the server side emitting
"[TTTS] [type : 3] [width : 2560] [height : 1280] [bitrate : 30000000]" with a
204-byte header.

The camera must already be in RVF / remote-viewfinder mode before the GET,
otherwise port 7679 is not listening.

Container ("TTT", a Samsung RIFF/AVI derivative). ALL integers are BIG-ENDIAN.
  Header:
    'TTTS' u32 size u32 type            (type&1 -> has video, type&2 -> has audio)
    'VID0' u32 size ... u32 videoCodecType (0=raw, 1=HEVC) ... u32 tsScale 'VD00' ...
    'AUD0' u32 size ... (0=raw, 1=AAC) ...
    'VRO0' u32 size ... 'VR00' ...      (gyro/orientation track)
    'LIST' u32 ...
    'movi'                              <- end of header, frame stream follows
  Frames:
    tag(4) = '00VD' video | '00AU' audio | '00VR' gyro
    u32 size ; u64 timestamp ; payload[size]
    For video, payload starts with the HEVC Annex-B start code 00 00 00 01,
    and payload[4] is the first NAL header byte: 0x40 => NAL type 32 (VPS),
    0x26 => NAL type 19 (IDR_W_RADL). Those are exactly the two values the
    Samsung app treats as "key frame", which is why the payload is believed to
    be plain Annex-B HEVC that ffmpeg can consume with no further processing.
"""
import socket
import struct
import sys
from urllib.parse import urlparse

TAG_TTTS = b"TTTS"
HEADER_TAGS = {b"TTTS", b"VID0", b"AUD0", b"VRO0", b"LIST", b"movi"}
FRAME_TAGS = {b"00VD": "video", b"00AU": "audio", b"00VR": "vrot"}


class Reader:
    def __init__(self, sock):
        self.f = sock.makefile("rb", buffering=1 << 20)

    def read(self, n):
        buf = self.f.read(n)
        if buf is None or len(buf) != n:
            raise EOFError("stream ended (wanted %d, got %d)" % (n, 0 if buf is None else len(buf)))
        return buf

    def u32(self):
        return struct.unpack(">I", self.read(4))[0]

    def u64(self):
        return struct.unpack(">Q", self.read(8))[0]

    def tag(self):
        return self.read(4)

    def skip(self, n):
        while n > 0:
            n -= len(self.read(min(n, 65536)))


def connect(url):
    u = urlparse(url)
    port = u.port or 80
    path = u.path or "/"
    s = socket.create_connection((u.hostname, port), timeout=15)
    s.settimeout(None)
    # The camera's DLNA/RVF HTTP server is picky; the official app sends
    # exactly this User-Agent on the streaming port.
    req = (
        "GET %s HTTP/1.1\r\n"
        "User-Agent: Android Linux\r\n"
        "Host: %s:%d\r\n"
        "Connection: Keep-Alive\r\n\r\n" % (path, u.hostname, port)
    )
    s.sendall(req.encode())
    return s


def read_http_headers(r):
    raw = b""
    while not raw.endswith(b"\r\n\r\n"):
        raw += r.read(1)
    return raw.decode("latin-1")


def parse_container_header(r, log):
    """Consume everything up to and including the 'movi' tag."""
    video_codec = None
    width = height = None
    while True:
        t = r.tag()
        if t == b"TTTS":
            size = r.u32()
            typ = r.u32()
            log("TTTS size=%d type=%d (video=%s audio=%s)" % (size, typ, bool(typ & 1), bool(typ & 2)))
        elif t == b"VID0":
            size = r.u32()
            r.skip(16)                      # transblocknumber, transblocktype, encodeW, encodeH
            video_codec = r.u32()
            r.skip(12)                      # bitrate, GOP, gopType
            _ts_scale = r.u32()
            sub = r.tag()
            if sub != b"VD00":
                raise ValueError("expected VD00, got %r" % sub)
            r.skip(4)                       # version
            num, den = r.u32(), r.u32()
            fps = num / den if den else 0.0
            r.skip(24)                      # horiAngle, vertiAngle, lensInfo (num/den pairs)
            width, height = r.u32(), r.u32()
            r.skip(8)
            log("VID0 size=%d codec=%d (1=HEVC) %dx%d %.3f fps" % (size, video_codec, width, height, fps))
        elif t == b"AUD0":
            size = r.u32()
            _channels = r.u32()
            r.skip(4)
            _ts_scale = r.u32()
            sub = r.tag()
            if sub != b"AU00":
                raise ValueError("expected AU00, got %r" % sub)
            r.skip(4)
            _audio_codec = r.u32()
            r.skip(32)
            _sample_rate = r.u32()
            r.skip(20)
            log("AUD0 size=%d codec=%d rate=%d ch=%d" % (size, _audio_codec, _sample_rate, _channels))
        elif t == b"VRO0":
            size = r.u32()
            r.skip(4)
            sub = r.tag()
            if sub != b"VR00":
                raise ValueError("expected VR00, got %r" % sub)
            r.skip(8)
            log("VRO0 size=%d (gyro track)" % size)
        elif t == b"LIST":
            r.skip(4)
        elif t == b"movi":
            log("movi -> frame stream begins")
            return video_codec, width, height
        else:
            raise ValueError("unexpected header tag %r" % t)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    url = sys.argv[1]

    def log(msg):
        sys.stderr.write("[ttt] %s\n" % msg)

    sock = connect(url)
    r = Reader(sock)
    hdr = read_http_headers(r)
    log("HTTP response: %s" % hdr.splitlines()[0])
    if "206" not in hdr and "200" not in hdr:
        log(hdr)
        return 1

    codec, w, h = parse_container_header(r, log)
    if codec is not None and codec != 1:
        log("WARNING: videoCodecType=%d is not 1 (HEVC); output may not be HEVC" % codec)

    out = sys.stdout.buffer
    nvideo = 0
    while True:
        try:
            t = r.tag()
        except EOFError:
            log("stream closed after %d video frames" % nvideo)
            return 0
        if t == TAG_TTTS:
            # Server re-emits the whole header mid-stream; resync.
            log("mid-stream TTTS, re-parsing header")
            size = r.u32()
            typ = r.u32()
            parse_container_header(r, log)
            continue
        kind = FRAME_TAGS.get(t)
        if kind is None:
            raise ValueError("lost sync: unexpected frame tag %r" % t)
        size = r.u32()
        _ts = r.u64()
        if kind == "vrot":
            # 6 x u32: yaw num/den, pitch num/den, roll num/den
            r.skip(24)
            continue
        payload = r.read(size)
        if kind == "video":
            out.write(payload)
            out.flush()
            nvideo += 1
        # audio (AAC) is dropped; add a second output pipe if you need it


if __name__ == "__main__":
    sys.exit(main())
