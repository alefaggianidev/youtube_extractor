"""Controllo periodico dei canali seguiti (e delle playlist da riassumere): mette in coda i video nuovi."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

from ytkb.config import Settings
from ytkb.db import Database
from ytkb.errors import PermanentError, TemporaryError
from ytkb.utils.timeutil import utcnow
from ytkb.youtube.channels import load_channels, sync_to_db
from ytkb.youtube.dataapi import DataApi
from ytkb.youtube.feeds import FeedEntry, channel_feed_url, fetch_feed, playlist_feed_url

log = logging.getLogger(__name__)


@dataclass
class PollStats:
    channels_ok: int = 0
    channels_failed: int = 0
    used_fallback: int = 0
    new_videos: list[str] = field(default_factory=list)
    skipped_shorts: int = 0
    errors: list[str] = field(default_factory=list)


class Monitor:
    def __init__(self, settings: Settings, db: Database, client: httpx.Client | None = None,
                 dataapi: DataApi | None = None, pause_s: float = 0.3):
        self.settings = settings
        self.db = db
        self.client = client or httpx.Client(follow_redirects=True)
        key = settings.secrets.reveal(settings.secrets.youtube_api_key)
        self.dataapi = dataapi or (DataApi(key, self.client) if key else None)
        self.pause_s = pause_s

    def _entries(self, channel_id: str, stats: PollStats) -> list[FeedEntry]:
        m = self.settings.monitor
        rss_error: Exception | None = None
        if m.rss_enabled:
            try:
                return fetch_feed(channel_feed_url(channel_id), self.client)
            except TemporaryError as exc:
                rss_error = exc
        if m.dataapi_fallback and self.dataapi is not None:
            stats.used_fallback += 1
            return self.dataapi.recent_uploads(channel_id)
        raise rss_error or TemporaryError("RSS disattivato e nessuna YOUTUBE_API_KEY per il piano B")

    def _enqueue(self, entries: list[FeedEntry], source: str, cutoff: datetime, stats: PollStats, *,
                 channel_title: str = "", skip_shorts: bool = True, priority: int = 0) -> None:
        candidates = [e for e in entries if e.published is None or e.published >= cutoff]
        known = self.db.known_video_ids([e.video_id for e in candidates])
        for e in candidates:
            if e.video_id in known:
                continue
            if skip_shorts and e.is_short:
                stats.skipped_shorts += 1
                continue
            if self.db.add_video(e.video_id, source=source, channel_id=e.channel_id,
                                 channel_title=e.channel_title or channel_title, title=e.title,
                                 published_at=e.published, priority=priority):
                stats.new_videos.append(e.video_id)
                log.info("🆕 %s — %s", e.channel_title or channel_title, e.title)

    def poll(self, now: datetime | None = None) -> PollStats:
        now = now or utcnow()
        stats = PollStats()
        channels = load_channels(self.settings.channels_file)
        sync_to_db(channels, self.db)
        cutoff = now - timedelta(hours=self.settings.monitor.lookback_hours)
        for ch in channels:
            if not ch.enabled:
                continue
            filters = self.settings.filters.merged(ch.filters)
            try:
                entries = self._entries(ch.id, stats)
                self._enqueue(entries, "rss", cutoff, stats, channel_title=ch.name, skip_shorts=filters.skip_shorts)
                self.db.mark_channel_polled(ch.id, ok=True, now=now)
                stats.channels_ok += 1
            except (TemporaryError, PermanentError) as exc:
                stats.channels_failed += 1
                stats.errors.append(f"{ch.name or ch.id}: {exc}")
                self.db.mark_channel_polled(ch.id, ok=False, error=str(exc)[:500], now=now)
                log.warning("Canale %s non controllato: %s", ch.name or ch.id, exc)
            if self.pause_s:
                time.sleep(self.pause_s)
        for pl in self.settings.monitor.watch_playlists:
            try:
                entries = fetch_feed(playlist_feed_url(pl), self.client)
                # una playlist "da riassumere" è una scelta tua: niente limite di data, priorità alta
                self._enqueue(entries, "playlist", datetime.min.replace(tzinfo=now.tzinfo), stats,
                              skip_shorts=False, priority=5)
            except TemporaryError as exc:
                stats.errors.append(f"playlist {pl}: {exc}")
                log.warning("Playlist %s non controllata: %s", pl, exc)
        self.db.kv_set("last_poll_at", now.isoformat(timespec="seconds"))
        if stats.new_videos or stats.channels_failed:
            log.info("Controllo canali: %d nuovi video, %d canali ok, %d con errori (%d con piano B)",
                     len(stats.new_videos), stats.channels_ok, stats.channels_failed, stats.used_fallback)
        return stats
