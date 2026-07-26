#!/usr/bin/env python3
"""
Empirically calibrate ffmpeg v360=dfisheye ih_fov/iv_fov for a Samsung Gear 360.

MODEL SCOPE: developed and tested against SM-C200 (2016) 3840x1920 dual-fisheye
video. It is a generic measurement, so it will also run on SM-R210 or on C200
still photos, but the RESULT will differ per resolution and per camera unit --
that is the point of running it.

Method: render the frame to equirectangular at a range of FOV values. In an
equirectangular output produced by v360=dfisheye the two hemispheres butt
together at output columns W/4 and 3W/4. The FOV that minimises the pixel
discontinuity across those two columns is the correct FOV.

Requires: ffmpeg, numpy, pillow.
Usage:  python3 c200_fov_calibrate.py FRAME.png [lo] [hi] [step]
        (extract a frame first:  ffmpeg -i clip.mp4 -frames:v 1 frame.png)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

# Poles are degenerate in equirectangular; only compare the middle band.
BAND_LO, BAND_HI = 0.20, 0.80
PROBE_W, PROBE_H = 1920, 960


def seam_discontinuity(frame: Path, fov: float, workdir: Path) -> float:
    """Mean abs difference across the two hemisphere seams at this FOV."""
    out = workdir / f"probe_{fov}.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(frame),
         "-vf", f"v360=dfisheye:e:ih_fov={fov}:iv_fov={fov},"
                f"scale={PROBE_W}:{PROBE_H}",
         "-y", str(out)],
        check=True,
    )
    a = np.asarray(Image.open(out).convert("L")).astype(float)
    h, w = a.shape
    band = a[int(h * BAND_LO):int(h * BAND_HI)]
    return float(np.mean([
        np.abs(band[:, s] - band[:, s - 1]).mean() for s in (w // 4, 3 * w // 4)
    ]))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    frame = Path(sys.argv[1])
    lo = float(sys.argv[2]) if len(sys.argv) > 2 else 180.0
    hi = float(sys.argv[3]) if len(sys.argv) > 3 else 200.0
    step = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    if not frame.is_file():
        print(f"error: no such frame: {frame}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        results = []
        fov = lo
        while fov <= hi + 1e-9:
            score = seam_discontinuity(frame, fov, workdir)
            results.append((fov, score))
            print(f"  ih_fov=iv_fov={fov:6.1f}  seam_MAD={score:8.3f}"
                  f"  {'#' * int(score * 4)}")
            fov += step

    best_fov, best_score = min(results, key=lambda t: t[1])
    print(f"\nBest fit: ih_fov=iv_fov={best_fov}  (seam_MAD={best_score:.3f})")
    print("Render with:")
    print(f'  ffmpeg -i IN.mp4 -vf "v360=dfisheye:e:'
          f'ih_fov={best_fov}:iv_fov={best_fov}" -c:a copy OUT.mp4')
    print("\nNOTE: a residual seam always remains. v360=dfisheye has no per-lens "
          "roll/pitch/yaw correction, and the two C200 lenses are not perfectly "
          "coaxial. For a seamless result use Hugin/.pto or fisheyeStitcher.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
