"""``channel_index.md``: l'indice di tutti i video analizzati di un canale (letto dal disco, non dal database)."""

from __future__ import annotations

import logging
from pathlib import Path

from ytkb.llm.schemas import AnalysisResult
from ytkb.models import VideoMeta
from ytkb.report import labels as L
from ytkb.report.render import _env
from ytkb.utils.fs import atomic_write_text
from ytkb.utils.timeutil import utcnow

log = logging.getLogger(__name__)


def update_channel_index(channel_dir: Path, tz_name: str) -> Path | None:
    rows = []
    channel_title = channel_dir.name.replace("_", " ")
    for video_dir in sorted(channel_dir.iterdir(), reverse=True):
        meta_p, analysis_p = video_dir / "metadata.json", video_dir / "analysis.json"
        if not (video_dir.is_dir() and meta_p.exists() and analysis_p.exists()):
            continue
        try:
            meta = VideoMeta.model_validate_json(meta_p.read_text(encoding="utf-8"))
            analysis = AnalysisResult.model_validate_json(analysis_p.read_text(encoding="utf-8"))
        except ValueError as exc:
            log.warning("Indice canale: salto %s (%s)", video_dir.name, exc)
            continue
        channel_title = meta.channel_title or channel_title
        rows.append({
            "date": video_dir.name[:10],
            "title": meta.title,
            "link": f"{video_dir.name}/report.md",
            "type": L.VIDEO_TYPE.get(analysis.video_type, analysis.video_type),
            "stars": L.stars(analysis.worth_watching.score),
            "assets": ", ".join(a.asset for a in analysis.assets[:6]),
        })
    if not rows:
        return None
    text = _env().get_template("channel_index.md.j2").render(
        channel=channel_title, rows=rows, updated=L.date_it(utcnow(), tz_name, with_time=True))
    path = channel_dir / "channel_index.md"
    atomic_write_text(path, text.strip() + "\n")
    return path
