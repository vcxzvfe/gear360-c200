"""Demultiplexer for the Samsung TTTS container used by the Gear 360 (SM-C200).

The camera's remote-view-finder stream is served on TCP 7679 as
``/livestream_high.avi``. Despite the ``.avi`` name, the ``video/x-avi``
Content-Type and a ``DLNA.ORG_PN=AVC_MP4_BL_CIF15_AAC_520`` content-features
header, it is none of those things: it is a Samsung "TTTS" container carrying
**HEVC**. No off-the-shelf player opens it. This module turns it into a raw
HEVC elementary stream that ffmpeg accepts directly.

Wire format, all big-endian, taken from ``cTTTWriter`` in the camera's own
``/usr/lib/libmmfcore.so`` (``Src/AVMuxer/cTTTWriter.cpp``) as recovered by the
firmware teardown -- see ``08-firmware-teardown.md`` section 1.4(c):

* A **224-byte header frame** beginning with the ASCII tag ``TTTS``. The 224
  figure is the firmware's own log string ("this is first packet but not a
  header frame (224 size) so drop this frame") and is authoritative; the
  field-by-field decomposition of those bytes is not, so this module skips the
  frame wholesale rather than pretending to parse it.
* Then a flat sequence of chunks::

      tag[4]  size:u32be  timestamp:u64be  payload[size]

  ``00VD`` carries video, ``00AU`` carries audio.
* On a video keyframe the codec header (VPS/SPS/PPS) is **prepended to the
  payload and counted in the size field**, so a caller that simply concatenates
  ``00VD`` payloads gets valid Annex-B HEVC with no special-casing.

Correction to prior community work: an Android-app-derived reconstruction of
this container that circulated previously lists a ``VRO0`` / ``00VR``
orientation track. The firmware writes ``ACC0`` / ``AC00`` instead, and a byte
scan of all 11,567 files in the extracted root filesystem finds **zero**
occurrences of ``VRO0`` or ``00VR``. This module follows the firmware.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import BinaryIO, Callable, Iterator, Protocol

__all__ = [
    "MAGIC",
    "HEADER_FRAME_SIZE",
    "TAG_VIDEO",
    "TAG_AUDIO",
    "Chunk",
    "DemuxStats",
    "TTTSError",
    "TruncatedStream",
    "BadMagic",
    "DesyncError",
    "iter_chunks",
    "demux_video",
    "open_stream",
    "build_synthetic",
]

MAGIC = b"TTTS"
HEADER_FRAME_SIZE = 224
TAG_VIDEO = b"00VD"
TAG_AUDIO = b"00AU"
TAG_SIZE = 4
SIZE_FIELD = 4
TIMESTAMP_FIELD = 8
CHUNK_PREFIX_SIZE = TAG_SIZE + SIZE_FIELD + TIMESTAMP_FIELD

#: Sanity bound on a single chunk. The stream is 2560x1280 HEVC at roughly
#: 22 Mbit/s, so even a keyframe carrying VPS/SPS/PPS stays far below this.
#: Its purpose is to fail fast on a desync instead of trying to allocate a
#: garbage length read out of misaligned bytes.
MAX_CHUNK_SIZE = 16 * 1024 * 1024

#: The camera's HTTP surface has been observed rejecting generic clients. The
#: official app sends this User-Agent on the streaming port.
USER_AGENT_APP = "Android Linux"
#: ``UPnPControlDevice::GetDeviceNameForAcl`` matches control-point identity by
#: *substring* against this pattern. Whether the ACL is ever armed is unknown,
#: but including it costs nothing and is the first thing to try on a 503.
USER_AGENT_RVF_PREFIX = "SEC_RVF_ML_"

DEFAULT_STREAM_PATH = "/livestream_high.avi"
#: The responder exposes five qualities, not one.
STREAM_PATHS = (
    "/livestream_high.avi",
    "/livestream_middle.avi",
    "/livestream_low.avi",
    "/livestream_recording.avi",
    "/livestream_gearvr.avi",
)


class TTTSError(Exception):
    """Base class for container-level failures."""


class TruncatedStream(TTTSError):
    """The stream ended in the middle of a structure."""


class BadMagic(TTTSError):
    """The first four bytes were not ``TTTS``."""


class DesyncError(TTTSError):
    """An unexpected tag or an implausible length was read."""


class Reader(Protocol):
    """Minimal byte source. Both sockets and files are adapted to this."""

    def read(self, n: int) -> bytes: ...


@dataclass(frozen=True)
class Chunk:
    """One demultiplexed record."""

    tag: bytes
    timestamp: int
    payload: bytes

    @property
    def is_video(self) -> bool:
        return self.tag == TAG_VIDEO

    @property
    def is_audio(self) -> bool:
        return self.tag == TAG_AUDIO


@dataclass(frozen=True)
class DemuxStats:
    """Summary of a demux run."""

    video_chunks: int
    audio_chunks: int
    other_chunks: int
    video_bytes: int
    first_timestamp: int | None
    last_timestamp: int | None

    @property
    def duration_ticks(self) -> int:
        if self.first_timestamp is None or self.last_timestamp is None:
            return 0
        return self.last_timestamp - self.first_timestamp


class _ExactReader:
    """Wraps a byte source and refuses to return short reads."""

    def __init__(self, inner: Reader) -> None:
        self._inner = inner

    def read_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._inner.read(n - len(buf))
            if not chunk:
                raise TruncatedStream(f"wanted {n} bytes, got {len(buf)}")
            buf.extend(chunk)
        return bytes(buf)

    def read_exact_or_eof(self, n: int) -> bytes | None:
        """Like :meth:`read_exact`, but returns ``None`` on a clean EOF."""
        try:
            first = self._inner.read(1)
        except (TimeoutError, socket.timeout):
            return None
        if not first:
            return None
        return first + self.read_exact(n - 1)


def iter_chunks(source: Reader, *, skip_header: bool = True) -> Iterator[Chunk]:
    """Yield every chunk in a TTTS stream.

    :param source: any object with a ``read(n)`` method.
    :param skip_header: consume and validate the 224-byte header frame first.
        Pass ``False`` if the caller already did so.
    :raises BadMagic: the stream does not start with ``TTTS``.
    :raises DesyncError: an unknown tag or an implausible chunk length.
    :raises TruncatedStream: the stream ended mid-structure.
    """
    reader = _ExactReader(source)

    if skip_header:
        header = reader.read_exact(HEADER_FRAME_SIZE)
        if not header.startswith(MAGIC):
            raise BadMagic(f"expected {MAGIC!r}, got {header[:4]!r}")

    while True:
        prefix = reader.read_exact_or_eof(CHUNK_PREFIX_SIZE)
        if prefix is None:
            return

        tag = prefix[:TAG_SIZE]

        # Defensive, not observed: if the server re-emits a header frame
        # mid-stream, resynchronise on it rather than treating it as a desync.
        if tag == MAGIC:
            reader.read_exact(HEADER_FRAME_SIZE - CHUNK_PREFIX_SIZE)
            continue

        if tag not in (TAG_VIDEO, TAG_AUDIO):
            raise DesyncError(f"unexpected tag {tag!r}")

        size = int.from_bytes(prefix[TAG_SIZE : TAG_SIZE + SIZE_FIELD], "big")
        timestamp = int.from_bytes(prefix[TAG_SIZE + SIZE_FIELD :], "big")

        if size > MAX_CHUNK_SIZE:
            raise DesyncError(
                f"chunk size {size} exceeds the {MAX_CHUNK_SIZE}-byte sanity bound; "
                "the stream is almost certainly misaligned"
            )

        yield Chunk(tag=tag, timestamp=timestamp, payload=reader.read_exact(size))


def demux_video(
    source: Reader,
    out: BinaryIO,
    *,
    skip_header: bool = True,
    on_chunk: Callable[[Chunk], None] | None = None,
) -> DemuxStats:
    """Write the HEVC elementary stream from ``source`` into ``out``.

    Video payloads are concatenated verbatim: on a keyframe the codec header is
    already prepended by the muxer and counted in the size field, so no
    parameter-set insertion is needed here.
    """
    video = audio = other = 0
    video_bytes = 0
    first_ts: int | None = None
    last_ts: int | None = None

    for chunk in iter_chunks(source, skip_header=skip_header):
        if first_ts is None:
            first_ts = chunk.timestamp
        last_ts = chunk.timestamp

        if chunk.is_video:
            out.write(chunk.payload)
            video += 1
            video_bytes += len(chunk.payload)
        elif chunk.is_audio:
            audio += 1
        else:  # pragma: no cover - iter_chunks rejects unknown tags
            other += 1

        if on_chunk is not None:
            on_chunk(chunk)

    return DemuxStats(
        video_chunks=video,
        audio_chunks=audio,
        other_chunks=other,
        video_bytes=video_bytes,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
    )


def open_stream(
    host: str,
    *,
    port: int = 7679,
    path: str = DEFAULT_STREAM_PATH,
    user_agent: str = USER_AGENT_APP,
    timeout: float = 15.0,
) -> tuple[socket.socket, bytes]:
    """Issue the streaming GET and return the socket plus the response head.

    The camera must already be in remote-view-finder mode; otherwise 7679 is
    not bound and this raises :class:`ConnectionRefusedError`.
    """
    sock = socket.create_connection((host, port), timeout=timeout)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"User-Agent: {user_agent}\r\n"
        f"Host: {host}:{port}\r\n"
        "Connection: Keep-Alive\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))

    head = bytearray()
    while b"\r\n\r\n" not in head:
        byte = sock.recv(1)
        if not byte:
            raise TruncatedStream("connection closed while reading response headers")
        head.extend(byte)
    return sock, bytes(head)


def build_synthetic(
    frames: list[tuple[bytes, int, bytes]],
    *,
    magic: bytes = MAGIC,
    header_size: int = HEADER_FRAME_SIZE,
) -> bytes:
    """Build a well-formed TTTS byte string. For tests and offline development.

    ``frames`` is a list of ``(tag, timestamp, payload)``.
    """
    out = bytearray(magic)
    out.extend(b"\x00" * (header_size - len(magic)))
    for tag, timestamp, payload in frames:
        out.extend(tag)
        out.extend(len(payload).to_bytes(SIZE_FIELD, "big"))
        out.extend(timestamp.to_bytes(TIMESTAMP_FIELD, "big"))
        out.extend(payload)
    return bytes(out)
