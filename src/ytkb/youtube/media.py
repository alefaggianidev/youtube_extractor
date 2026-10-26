"""Stadio 5: cattura chirurgica (D-004, D-014).

Una sola chiamata yt-dlp scarica **solo pochi secondi** attorno a ciascun momento scelto (solo video, max 1080p);
poi ``ffmpeg`` estrae qualche fotogramma da ogni pezzetto. Opzionalmente produce micro-clip H.264.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ytkb.config import Settings
from ytkb.errors import PermanentError, TemporaryError
from ytkb.youtube.urls import watch_url
from ytkb.youtube.ytdlp import base_options, classify_error

log = logging.getLogger(__name__)

Downloader = Callable[[str, dict[str, Any]], None]
_SECTION_FILE = re.compile(r"^sec_(\d+(?:\.\d+)?)\.")


@dataclass(frozen=True)
class Section:
    start: float
    end: float


def video_format(height: int) -> str:
    """Solo video (niente audio: servono immagini), preferendo H.264 che ffmpeg decodifica ovunque."""
    h = int(height)
    return (f"bv*[height<={h}][vcodec^=avc1]/bv*[height<={h}]/b[height<={h}]/bv*/b")


def clip_format(height: int = 720) -> str:
    return f"b[height<={height}][ext=mp4]/bv*[height<={height}]+ba/b[height<={height}]/b"


def capture_options(settings: Settings, sections: Sequence[Section], out_dir: Path, *, with_audio: bool,
                    height: int) -> dict[str, Any]:
    from yt_dlp.utils import download_range_func

    return base_options(settings) | {
        "format": clip_format(height) if with_audio else video_format(height),
        "download_ranges": download_range_func(None, [(s.start, s.end) for s in sections]),
        "force_keyframes_at_cuts": False,
        "outtmpl": {"default": str(out_dir / "sec_%(section_start)s.%(ext)s")},
        "overwrites": True,
        "skip_download": False,
    }


def _default_download(url: str, opts: dict[str, Any]) -> None:
    import yt_dlp

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise PermanentError("ffmpeg non trovato: è necessario per estrarre i fotogrammi")
    return exe


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60)
    try:
        return float(json.loads(out.stdout or "{}").get("format", {}).get("duration", 0) or 0)
    except (ValueError, TypeError):
        return 0.0


def extract_frames(video: Path, count: int, out_dir: Path, prefix: str) -> list[Path]:
    """Estrae ``count`` fotogrammi distribuiti uniformemente nel file video."""
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video) or 3.0
    frames: list[Path] = []
    for i in range(max(1, count)):
        t = duration * (i + 0.5) / max(1, count)
        target = out_dir / f"{prefix}_{i:02d}.jpg"
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
               "-frames:v", "1", "-q:v", "2", str(target)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and target.exists() and target.stat().st_size > 0:
            frames.append(target)
        else:
            log.debug("ffmpeg non ha estratto il frame %s: %s", target.name, res.stderr.strip()[:300])
    return frames


def _match_files(tmp: Path, sections: Sequence[Section]) -> dict[int, Path]:
    """Associa i file scaricati (sec_<inizio>.<ext>) alle sezioni richieste."""
    found: dict[int, Path] = {}
    for f in sorted(tmp.iterdir()):
        m = _SECTION_FILE.match(f.name)
        if not m or f.suffix in (".part", ".ytdl", ".json"):
            continue
        start = float(m.group(1))
        idx = min(range(len(sections)), key=lambda i: abs(sections[i].start - start))
        if abs(sections[idx].start - start) <= 1.0 and idx not in found:
            found[idx] = f
    return found


@dataclass
class CaptureResult:
    frames: dict[int, list[Path]]  # indice del momento -> fotogrammi candidati
    tmp: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


class FrameCapturer:
    def __init__(self, settings: Settings, downloader: Downloader | None = None):
        self._settings = settings
        self._download = downloader or _default_download

    def _download_sections(self, video_id: str, sections: Sequence[Section], tmp: Path, *, with_audio: bool,
                           height: int) -> dict[int, Path]:
        opts = capture_options(self._settings, sections, tmp, with_audio=with_audio, height=height)
        try:
            self._download(watch_url(video_id), opts)
        except Exception as exc:  # noqa: BLE001
            err = classify_error(exc)
            raise err from exc
        files = _match_files(tmp, sections)
        if not files:
            raise TemporaryError("yt-dlp non ha prodotto nessun file per le sezioni richieste")
        return files

    def capture_frames(self, video_id: str, moments: Sequence[float],
                       frames_per_moment: int | None = None) -> CaptureResult:
        """Per ogni momento (in secondi) restituisce i fotogrammi candidati, in una cartella temporanea.

        Il chiamante sceglie il migliore, lo copia nell'archivio e poi chiama ``result.cleanup()``.
        """
        v = self._settings.visual
        n = frames_per_moment or v.frames_per_trigger
        sections = [Section(max(0.0, t - v.capture_window_s), t + v.capture_window_s) for t in moments]
        tmp = Path(tempfile.mkdtemp(prefix=f"cap_{video_id}_", dir=self._settings.work_dir))
        result = CaptureResult(frames={}, tmp=tmp)
        try:
            files = self._download_sections(video_id, sections, tmp, with_audio=False, height=v.capture_height)
            for idx, f in files.items():
                result.frames[idx] = extract_frames(f, n, tmp / "frames", prefix=f"m{idx:02d}")
        except BaseException:
            result.cleanup()
            raise
        return result

    def capture_clips(self, video_id: str, ranges: Sequence[tuple[float, float]], out_paths: Sequence[Path]) -> list[Path]:
        """Micro-clip H.264/AAC (opzionali). Restituisce i file creati."""
        sections = [Section(max(0.0, a), max(a + 1, b)) for a, b in ranges]
        created: list[Path] = []
        with tempfile.TemporaryDirectory(prefix=f"clip_{video_id}_", dir=self._settings.work_dir) as tmpdir:
            files = self._download_sections(video_id, sections, Path(tmpdir), with_audio=True, height=720)
            for idx, src in files.items():
                dst = out_paths[idx]
                dst.parent.mkdir(parents=True, exist_ok=True)
                cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-c:v", "libx264",
                       "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                       str(dst)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if res.returncode == 0 and dst.exists():
                    created.append(dst)
                else:
                    log.warning("Clip non creata (%s): %s", dst.name, res.stderr.strip()[:300])
        return created
