"""End-to-end check: real HEVC -> TTTS -> demuxer -> ffmpeg decodes it.

The unit tests prove the parser implements the specification. They cannot
prove the specification produces something a player will accept, because they
only ever move synthetic bytes around. This test closes that gap with real
codec data: ffmpeg encodes an HEVC elementary stream at the camera's own
resolution, the stream is split at access-unit boundaries and wrapped in TTTS
records the way ``cTTTWriter`` would, the demuxer unwraps it, and ffmpeg is
asked to decode the result.

It still does not prove the container specification matches the camera --
only a capture from real hardware can do that, and none exists yet. What it
does prove is that if the specification is right, this code produces playable
video.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.ttts import TAG_AUDIO, TAG_VIDEO, build_synthetic, demux_video

pytestmark = pytest.mark.integration

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_ffmpeg = pytest.mark.skipif(
    not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed"
)

START_CODE = b"\x00\x00\x00\x01"
#: The stream the camera actually serves on /livestream_high.avi.
CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS = 2560, 1280, 30


def _split_access_units(stream: bytes) -> list[bytes]:
    """Group NAL units into access units, parameter sets leading their slice.

    This mirrors the muxer's documented behaviour: on a keyframe the VPS/SPS/PPS
    are prepended to the payload and counted in the size field.
    """
    positions = []
    pos = stream.find(START_CODE)
    while pos != -1:
        positions.append(pos)
        pos = stream.find(START_CODE, pos + 4)
    if not positions:
        return [stream]

    nals = [
        stream[start : positions[i + 1]] if i + 1 < len(positions) else stream[start:]
        for i, start in enumerate(positions)
    ]

    units: list[bytes] = []
    pending = b""
    for nal in nals:
        nal_type = (nal[4] >> 1) & 0x3F
        is_parameter_set = nal_type in (32, 33, 34)  # VPS, SPS, PPS
        if is_parameter_set:
            pending += nal
        else:
            units.append(pending + nal)
            pending = b""
    if pending:
        units.append(pending)
    return units


@requires_ffmpeg
def test_real_hevc_survives_the_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.hevc"
    subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", f"testsrc=size={CAMERA_WIDTH}x{CAMERA_HEIGHT}:rate={CAMERA_FPS}:duration=1",
            "-c:v", "libx265", "-x265-params", "log-level=none",
            "-f", "hevc", str(source),
        ],
        check=True,
        capture_output=True,
    )
    original = source.read_bytes()
    assert original, "ffmpeg produced no HEVC"

    units = _split_access_units(original)
    assert len(units) > 1, "expected several access units to exercise chunking"

    # Interleave audio so the demuxer has to discard something, as it will live.
    frames: list[tuple[bytes, int, bytes]] = []
    for index, unit in enumerate(units):
        frames.append((TAG_VIDEO, index * 3003, unit))
        if index % 3 == 0:
            frames.append((TAG_AUDIO, index * 3003, b"\x21" * 64))

    container = tmp_path / "capture.ttts"
    container.write_bytes(build_synthetic(frames))

    recovered = tmp_path / "out.hevc"
    with container.open("rb") as src, recovered.open("wb") as dst:
        stats = demux_video(src, dst)

    assert stats.video_chunks == len(units)
    assert stats.audio_chunks == sum(1 for i in range(len(units)) if i % 3 == 0)

    # Byte-identical: the demuxer must not alter the elementary stream.
    assert recovered.read_bytes() == original

    probe = subprocess.run(
        [
            FFPROBE, "-hide_banner", "-loglevel", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height",
            "-of", "csv=p=0", str(recovered),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip().startswith(
        f"hevc,{CAMERA_WIDTH},{CAMERA_HEIGHT}"
    ), probe.stdout


@requires_ffmpeg
def test_demuxed_output_actually_decodes_to_frames(tmp_path: Path) -> None:
    """ffprobe reading a header is weaker evidence than a decoder emitting pixels."""
    source = tmp_path / "source.hevc"
    subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x320:rate=30:duration=1",
            "-c:v", "libx265", "-x265-params", "log-level=none",
            "-f", "hevc", str(source),
        ],
        check=True,
        capture_output=True,
    )

    container = build_synthetic(
        [
            (TAG_VIDEO, i * 3003, unit)
            for i, unit in enumerate(_split_access_units(source.read_bytes()))
        ]
    )
    demuxed = tmp_path / "out.hevc"
    import io

    with demuxed.open("wb") as dst:
        demux_video(io.BytesIO(container), dst)

    decoded = subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "hevc", "-i", str(demuxed),
            "-frames:v", "5", "-f", "rawvideo", "-pix_fmt", "yuv420p",
            str(tmp_path / "frames.yuv"),
        ],
        capture_output=True,
        text=True,
    )
    assert decoded.returncode == 0, decoded.stderr
    frame_bytes = (tmp_path / "frames.yuv").stat().st_size
    assert frame_bytes == 5 * 640 * 320 * 3 // 2, frame_bytes
