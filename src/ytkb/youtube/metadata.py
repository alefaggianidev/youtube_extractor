"""Stadio 1: informazioni sul video tramite yt-dlp, senza scaricare nulla."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from ytkb.config import Settings
from ytkb.models import Chapter, LiveStatus, VideoMeta
from ytkb.youtube.urls import watch_url
from ytkb.youtube.ytdlp import base_options, classify_error

log = logging.getLogger(__name__)


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), UTC) if value else None
    except (TypeError, ValueError, OSError):
        return None


def _upload_date(value: str | None) -> date | None:
    if not value or len(value) != 8:
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def meta_from_info(info: dict[str, Any]) -> VideoMeta:
    """Converte il dizionario di yt-dlp nel nostro modello (funzione pura, testabile con una fixture)."""
    upload = _upload_date(info.get("upload_date"))
    published = _ts(info.get("timestamp"))
    if published is None and upload is not None:
        published = datetime(upload.year, upload.month, upload.day, tzinfo=UTC)
    try:
        live = LiveStatus(info.get("live_status") or "unknown")
    except ValueError:
        live = LiveStatus.UNKNOWN
    webpage = info.get("webpage_url") or info.get("original_url") or ""
    media_type = info.get("media_type") or ("short" if "/shorts/" in webpage else "video")
    chapters = []
    for ch in info.get("chapters") or []:
        try:
            chapters.append(Chapter(title=str(ch.get("title") or ""), start_s=float(ch.get("start_time") or 0),
                                    end_s=float(ch["end_time"]) if ch.get("end_time") is not None else None))
        except (TypeError, ValueError):
            continue
    handle = info.get("uploader_id") or ""
    return VideoMeta(
        video_id=info["id"],
        title=info.get("title") or info.get("fulltitle") or info["id"],
        channel_id=info.get("channel_id") or "",
        channel_title=info.get("channel") or info.get("uploader") or "",
        channel_handle=handle if str(handle).startswith("@") else "",
        upload_date=upload,
        published_at=published,
        release_at=_ts(info.get("release_timestamp")),
        duration_s=float(info["duration"]) if info.get("duration") else None,
        live_status=live,
        media_type=media_type,
        availability=info.get("availability") or "unknown",
        language=info.get("language") or None,
        description=(info.get("description") or "")[:5000],
        tags=list(info.get("tags") or [])[:30],
        chapters=chapters,
        width=info.get("width"),
        height=info.get("height"),
        thumbnail=info.get("thumbnail") or "",
        subtitle_langs=sorted(k for k in (info.get("subtitles") or {}) if k != "live_chat"),
        auto_caption_langs=sorted((info.get("automatic_captions") or {}).keys()),
    )


def fetch_metadata(video_id: str, settings: Settings) -> VideoMeta:
    """Chiede a YouTube (via yt-dlp) i metadati del video. Solleva errori tipizzati (vedi ``errors.py``)."""
    import yt_dlp

    opts = base_options(settings) | {
        "skip_download": True,
        "ignore_no_formats_error": True,  # le premiere/live future restituiscono comunque i metadati
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(watch_url(video_id), download=False, process=False)
    except Exception as exc:  # noqa: BLE001 - yt-dlp solleva DownloadError/ExtractorError generici
        raise classify_error(exc) from exc
    if not info or not info.get("id"):
        raise classify_error(RuntimeError("yt-dlp non ha restituito informazioni"))
    return meta_from_info(info)
