"""Immagini per l'HTML autocontenuto: ridimensionate e incorporate come data URI."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image


def to_data_uri(path: Path, max_width: int = 1600, quality: int = 80) -> str:
    with Image.open(path) as img:
        img = img.convert("RGB")
        if img.width > max_width:
            img = img.resize((max_width, round(img.height * max_width / img.width)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
