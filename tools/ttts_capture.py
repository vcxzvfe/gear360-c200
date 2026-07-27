#!/usr/bin/env python3
"""Capture the Gear 360 (SM-C200) live stream and emit raw HEVC.

The camera must already be in remote-view-finder mode -- TCP 7679 is not bound
otherwise, and this will report a refused connection. Entering RVF is a
separate, unsolved problem; see ``08-firmware-teardown.md``.

Play live::

    python3 ttts_capture.py 192.168.107.1 - | ffplay -f hevc -fflags nobuffer -i -

Record to a file, then inspect::

    python3 ttts_capture.py 192.168.107.1 out.hevc
    ffprobe out.hevc

Re-demux an already-captured raw container::

    python3 ttts_capture.py --from-file cam.ttts out.hevc

Add ``--raw cam.ttts`` to keep the untouched container bytes as well. Do that
on a first successful capture: it is the artifact that lets the container
specification be re-checked offline, and nobody has ever published one.
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import sys
from typing import BinaryIO

from ttts import (
    DEFAULT_STREAM_PATH,
    STREAM_PATHS,
    USER_AGENT_APP,
    USER_AGENT_RVF_PREFIX,
    TTTSError,
    demux_video,
    open_stream,
)

EXIT_OK = 0
EXIT_STREAM_ERROR = 1
EXIT_UNREACHABLE = 2


class _TeeReader:
    """Passes bytes through while also writing them to a side file."""

    def __init__(self, inner: socket.socket, sink: BinaryIO) -> None:
        self._inner = inner
        self._sink = sink

    def read(self, n: int) -> bytes:
        data = self._inner.recv(n)
        if data:
            self._sink.write(data)
        return data


class _SocketReader:
    def __init__(self, inner: socket.socket) -> None:
        self._inner = inner

    def read(self, n: int) -> bytes:
        return self._inner.recv(n)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture the SM-C200 RVF stream and write raw HEVC.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("host", nargs="?", help="camera address, e.g. 192.168.107.1")
    parser.add_argument(
        "output", nargs="?", default="-", help="HEVC output path, or - for stdout"
    )
    parser.add_argument("--port", type=int, default=7679)
    parser.add_argument(
        "--path",
        default=DEFAULT_STREAM_PATH,
        choices=STREAM_PATHS,
        help="which of the five advertised qualities to request",
    )
    parser.add_argument(
        "--rvf-user-agent",
        action="store_true",
        help=(
            "send a SEC_RVF_ML_-prefixed User-Agent. The device matches "
            "control-point identity by substring against that pattern; try this "
            "first if the camera answers 503."
        ),
    )
    parser.add_argument("--raw", help="also write the untouched container bytes here")
    parser.add_argument("--from-file", help="demux a saved container instead of a socket")
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.from_file and not args.host:
        _build_parser().error("give a camera address, or --from-file")

    out: BinaryIO
    with contextlib.ExitStack() as stack:
        if args.output == "-":
            out = sys.stdout.buffer
        else:
            out = stack.enter_context(open(args.output, "wb"))

        if args.from_file:
            source = stack.enter_context(open(args.from_file, "rb"))
            print(f"demuxing {args.from_file}", file=sys.stderr)
        else:
            user_agent = (
                USER_AGENT_RVF_PREFIX + "mac"
                if args.rvf_user_agent
                else USER_AGENT_APP
            )
            try:
                sock, head = open_stream(
                    args.host,
                    port=args.port,
                    path=args.path,
                    user_agent=user_agent,
                    timeout=args.timeout,
                )
            except ConnectionRefusedError:
                print(
                    f"{args.host}:{args.port} refused the connection.\n"
                    "That port only binds while the camera is in remote-view-finder "
                    "mode, so this is the expected result unless RVF is already "
                    "running.",
                    file=sys.stderr,
                )
                return EXIT_UNREACHABLE
            except OSError as exc:
                print(f"cannot reach {args.host}:{args.port}: {exc}", file=sys.stderr)
                return EXIT_UNREACHABLE

            stack.callback(sock.close)
            status = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            print(f"< {status}", file=sys.stderr)
            if b" 503 " in head or b" 401 " in head:
                print(
                    "The camera refused this client. Retry with --rvf-user-agent.",
                    file=sys.stderr,
                )
                return EXIT_STREAM_ERROR

            if args.raw:
                raw_sink = stack.enter_context(open(args.raw, "wb"))
                source = _TeeReader(sock, raw_sink)
            else:
                source = _SocketReader(sock)

        try:
            stats = demux_video(source, out)
        except KeyboardInterrupt:
            print("\ninterrupted", file=sys.stderr)
            return EXIT_OK
        except TTTSError as exc:
            print(f"container error: {exc}", file=sys.stderr)
            return EXIT_STREAM_ERROR

    print(
        f"{stats.video_chunks} video chunks, {stats.video_bytes} bytes of HEVC, "
        f"{stats.audio_chunks} audio chunks, timestamp span {stats.duration_ticks}",
        file=sys.stderr,
    )
    if stats.video_chunks == 0:
        print(
            "No video arrived. The header was valid, so the container is right, "
            "but the camera sent no frames.",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
