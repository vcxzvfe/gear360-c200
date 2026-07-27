"""Tests for the TTTS demultiplexer.

These run against synthetic containers built to the specification recovered
from the camera's own muxer. They cannot prove the specification is right --
only a capture from real hardware can do that -- but they do prove the parser
implements the specification, handles short reads the way a socket produces
them, and fails loudly instead of silently emitting garbage.
"""

from __future__ import annotations

import io

import pytest

from tools.ttts import (
    CHUNK_PREFIX_SIZE,
    HEADER_FRAME_SIZE,
    MAGIC,
    MAX_CHUNK_SIZE,
    TAG_AUDIO,
    TAG_VIDEO,
    BadMagic,
    DesyncError,
    TruncatedStream,
    build_synthetic,
    demux_video,
    iter_chunks,
)


class DribbleReader:
    """Returns at most ``limit`` bytes per call.

    A real socket does this constantly and it is the classic way a demuxer
    that assumes ``read(n)`` returns ``n`` bytes corrupts a stream.
    """

    def __init__(self, data: bytes, limit: int = 1) -> None:
        self._data = data
        self._pos = 0
        self._limit = limit

    def read(self, n: int) -> bytes:
        take = min(n, self._limit)
        chunk = self._data[self._pos : self._pos + take]
        self._pos += len(chunk)
        return chunk


VIDEO_KEYFRAME = b"\x00\x00\x00\x01\x40\x01" + b"\xaa" * 40
VIDEO_DELTA = b"\x00\x00\x00\x01\x02\x01" + b"\xbb" * 20
AUDIO_FRAME = b"\xde\xad\xbe\xef"


@pytest.mark.unit
def test_round_trip_concatenates_video_payloads_in_order() -> None:
    data = build_synthetic(
        [
            (TAG_VIDEO, 0, VIDEO_KEYFRAME),
            (TAG_AUDIO, 10, AUDIO_FRAME),
            (TAG_VIDEO, 33, VIDEO_DELTA),
        ]
    )
    out = io.BytesIO()
    stats = demux_video(io.BytesIO(data), out)

    assert out.getvalue() == VIDEO_KEYFRAME + VIDEO_DELTA
    assert stats.video_chunks == 2
    assert stats.audio_chunks == 1
    assert stats.video_bytes == len(VIDEO_KEYFRAME) + len(VIDEO_DELTA)
    assert stats.first_timestamp == 0
    assert stats.last_timestamp == 33
    assert stats.duration_ticks == 33


@pytest.mark.unit
def test_survives_one_byte_at_a_time_reads() -> None:
    """The socket case. Byte-at-a-time must give a byte-identical result."""
    data = build_synthetic(
        [(TAG_VIDEO, 0, VIDEO_KEYFRAME), (TAG_VIDEO, 33, VIDEO_DELTA)]
    )
    whole = io.BytesIO()
    demux_video(io.BytesIO(data), whole)

    dribbled = io.BytesIO()
    demux_video(DribbleReader(data, limit=1), dribbled)

    assert dribbled.getvalue() == whole.getvalue()


@pytest.mark.unit
@pytest.mark.parametrize("limit", [1, 3, 7, 64, 4096])
def test_result_is_independent_of_read_granularity(limit: int) -> None:
    data = build_synthetic(
        [(TAG_VIDEO, i, bytes([i]) * (i + 1)) for i in range(1, 12)]
    )
    out = io.BytesIO()
    demux_video(DribbleReader(data, limit=limit), out)
    assert out.getvalue() == b"".join(bytes([i]) * (i + 1) for i in range(1, 12))


@pytest.mark.unit
def test_empty_stream_after_header_is_not_an_error() -> None:
    """RVF can be entered with nothing yet encoded; that is not a failure."""
    out = io.BytesIO()
    stats = demux_video(io.BytesIO(build_synthetic([])), out)

    assert out.getvalue() == b""
    assert stats.video_chunks == 0
    assert stats.first_timestamp is None
    assert stats.duration_ticks == 0


@pytest.mark.unit
def test_rejects_a_stream_that_does_not_start_with_ttts() -> None:
    data = build_synthetic([(TAG_VIDEO, 0, VIDEO_DELTA)], magic=b"RIFF")
    with pytest.raises(BadMagic):
        demux_video(io.BytesIO(data), io.BytesIO())


@pytest.mark.unit
def test_truncated_header_frame_raises() -> None:
    with pytest.raises(TruncatedStream):
        demux_video(io.BytesIO(MAGIC + b"\x00" * 10), io.BytesIO())


@pytest.mark.unit
def test_truncated_payload_raises_rather_than_emitting_a_short_frame() -> None:
    data = build_synthetic([(TAG_VIDEO, 0, VIDEO_KEYFRAME)])
    with pytest.raises(TruncatedStream):
        demux_video(io.BytesIO(data[:-5]), io.BytesIO())


@pytest.mark.unit
def test_unknown_tag_raises_desync() -> None:
    data = build_synthetic([(b"XXXX", 0, b"junk")])
    with pytest.raises(DesyncError, match="unexpected tag"):
        demux_video(io.BytesIO(data), io.BytesIO())


@pytest.mark.unit
def test_vro0_is_not_accepted() -> None:
    """The Android-derived reconstruction claimed a VRO0/00VR track.

    The firmware writes ACC0/AC00 and a byte scan of the extracted root
    filesystem finds zero occurrences of VRO0 or 00VR. If a real capture ever
    contains 00VR this test is what should fail, loudly, rather than the
    parser silently skipping the record.
    """
    data = build_synthetic([(b"00VR", 0, b"\x01" * 24)])
    with pytest.raises(DesyncError):
        demux_video(io.BytesIO(data), io.BytesIO())


@pytest.mark.unit
def test_implausible_length_is_rejected_before_allocating() -> None:
    body = bytearray(MAGIC + b"\x00" * (HEADER_FRAME_SIZE - len(MAGIC)))
    body.extend(TAG_VIDEO)
    body.extend((MAX_CHUNK_SIZE + 1).to_bytes(4, "big"))
    body.extend((0).to_bytes(8, "big"))
    with pytest.raises(DesyncError, match="sanity bound"):
        demux_video(io.BytesIO(bytes(body)), io.BytesIO())


@pytest.mark.unit
def test_midstream_header_frame_resynchronises() -> None:
    """Defensive path: a re-emitted header must not desync the parser."""
    first = build_synthetic([(TAG_VIDEO, 0, VIDEO_KEYFRAME)])
    second = build_synthetic([(TAG_VIDEO, 33, VIDEO_DELTA)])
    out = io.BytesIO()
    stats = demux_video(io.BytesIO(first + second), out)

    assert out.getvalue() == VIDEO_KEYFRAME + VIDEO_DELTA
    assert stats.video_chunks == 2


@pytest.mark.unit
def test_chunk_prefix_layout_matches_the_specification() -> None:
    """4-byte tag + u32be size + u64be timestamp = 16 bytes, big-endian."""
    assert CHUNK_PREFIX_SIZE == 16
    assert HEADER_FRAME_SIZE == 224

    payload = b"\x11" * 5
    data = build_synthetic([(TAG_VIDEO, 0x0102030405060708, payload)])
    record = data[HEADER_FRAME_SIZE:]

    assert record[0:4] == TAG_VIDEO
    assert record[4:8] == (5).to_bytes(4, "big")
    assert record[8:16] == bytes.fromhex("0102030405060708")
    assert record[16:] == payload


@pytest.mark.unit
def test_iter_chunks_exposes_timestamps_and_kind() -> None:
    data = build_synthetic(
        [(TAG_VIDEO, 7, VIDEO_DELTA), (TAG_AUDIO, 9, AUDIO_FRAME)]
    )
    chunks = list(iter_chunks(io.BytesIO(data)))

    assert [c.timestamp for c in chunks] == [7, 9]
    assert [c.is_video for c in chunks] == [True, False]
    assert [c.is_audio for c in chunks] == [False, True]
