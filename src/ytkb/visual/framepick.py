"""Scelta del fotogramma migliore (D-011): Pillow + numpy, niente OpenCV.

- **nitidezza** = varianza del Laplaciano (più bordi netti → valore più alto: testo e grafici leggibili);
- **frame uniformi** (dissolvenze, schermo nero/bianco) = deviazione standard molto bassa → scartati.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image


def load_gray(path: Path, max_width: int = 960) -> np.ndarray:
    with Image.open(path) as img:
        img = img.convert("L")
        if img.width > max_width:
            img = img.resize((max_width, round(img.height * max_width / img.width)), Image.Resampling.BILINEAR)
        return np.asarray(img, dtype=np.float32)


def sharpness(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    c = gray[1:-1, 1:-1]
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * c
    return float(lap.var())


def is_uniform(gray: np.ndarray, std_threshold: float = 6.0) -> bool:
    return float(gray.std()) < std_threshold


def pick_best(paths: Sequence[Path]) -> Path | None:
    """Il fotogramma più nitido tra i candidati, escludendo quelli uniformi. ``None`` se nessuno è utilizzabile."""
    best: tuple[float, Path] | None = None
    for p in paths:
        try:
            gray = load_gray(p)
        except OSError:
            continue
        if is_uniform(gray):
            continue
        score = sharpness(gray)
        if best is None or score > best[0]:
            best = (score, p)
    return best[1] if best else None
