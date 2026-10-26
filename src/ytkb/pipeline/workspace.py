"""Cartella di un video nell'archivio, con gli artefatti di ogni stadio (checkpoint, D-008).

Struttura: ``archive/<Canale>/<YYYY-MM-DD>_<Titolo>_[<VIDEO_ID>]/``
"""

from __future__ import annotations

import glob
import shutil
from datetime import date
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from ytkb.models import Stage, VideoMeta
from ytkb.utils.fs import atomic_write_json, atomic_write_text
from ytkb.utils.text import sanitize_filename

M = TypeVar("M", bound=BaseModel)

METADATA = "metadata.json"
TRANSCRIPT = "transcript.json"
TRANSCRIPT_TXT = "transcript.txt"
ANALYSIS = "analysis.json"
VISUAL = "visual.json"
REPORT_MD = "report.md"
REPORT_HTML = "report.html"

# Quali artefatti vanno cancellati per rifare la pipeline da un certo stadio in poi (--from).
_INVALIDATES: dict[Stage, list[str]] = {
    Stage.METADATA: [METADATA, TRANSCRIPT, TRANSCRIPT_TXT, ANALYSIS, VISUAL],
    Stage.TRANSCRIPT: [TRANSCRIPT, TRANSCRIPT_TXT, ANALYSIS, VISUAL],
    Stage.ANALYSIS: [ANALYSIS, VISUAL],
    Stage.LOCATE: [VISUAL],
    Stage.CAPTURE: [VISUAL],
    Stage.READ: [VISUAL],
    Stage.RENDER: [],
    Stage.PUBLISH: [],
}


def channel_dir_name(meta: VideoMeta) -> str:
    return sanitize_filename(meta.channel_title or meta.channel_id or "Canale_sconosciuto", max_len=60)


def video_dir_name(meta: VideoMeta, tz_name: str) -> str:
    if meta.published_at:
        day = meta.published_at.astimezone(ZoneInfo(tz_name)).date()
    else:
        day = meta.upload_date or date.today()
    return f"{day.isoformat()}_{sanitize_filename(meta.title, max_len=60)}_[{meta.video_id}]"


def find_existing(archive_dir: Path, video_id: str) -> Path | None:
    """Cerca una cartella già esistente per il video (il titolo può essere cambiato nel frattempo)."""
    pattern = str(archive_dir / "*" / f"*_{glob.escape(f'[{video_id}]')}")
    matches = sorted(glob.glob(pattern))
    return Path(matches[0]) if matches else None


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def for_video(cls, archive_dir: Path, meta: VideoMeta, tz_name: str, known: str | None = None) -> Workspace:
        if known and Path(known).exists():
            return cls(Path(known))
        existing = find_existing(archive_dir, meta.video_id)
        if existing:
            return cls(existing)
        return cls(archive_dir / channel_dir_name(meta) / video_dir_name(meta, tz_name))

    # --- percorsi --------------------------------------------------------------------
    def path(self, name: str) -> Path:
        return self.root / name

    @property
    def frames_dir(self) -> Path:
        return self.root / "frames"

    @property
    def clips_dir(self) -> Path:
        return self.root / "clips"

    @property
    def channel_dir(self) -> Path:
        return self.root.parent

    # --- artefatti -------------------------------------------------------------------
    def has(self, name: str) -> bool:
        return self.path(name).exists()

    def load(self, name: str, model: type[M]) -> M | None:
        p = self.path(name)
        if not p.exists():
            return None
        try:
            return model.model_validate_json(p.read_text(encoding="utf-8"))
        except ValueError:
            return None  # artefatto corrotto o di una versione vecchia: lo stadio verrà rifatto

    def save(self, name: str, obj: BaseModel) -> None:
        atomic_write_json(self.path(name), obj.model_dump(mode="json"))

    def write_text(self, name: str, text: str) -> None:
        atomic_write_text(self.path(name), text)

    def invalidate_from(self, stage: Stage) -> None:
        for name in _INVALIDATES.get(stage, []):
            self.path(name).unlink(missing_ok=True)
        if stage in (Stage.METADATA, Stage.TRANSCRIPT, Stage.ANALYSIS, Stage.LOCATE, Stage.CAPTURE):
            for d in (self.frames_dir, self.clips_dir):
                if d.exists():
                    shutil.rmtree(d)
