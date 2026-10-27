"""Feed RSS (Atom) di YouTube: canali e playlist pubbliche, senza quote e senza login (D-009).

Attenzione: il feed mostra solo gli ultimi 15 video e a volte risponde 404 per ore (problema noto di YouTube):
in quel caso si usa la YouTube Data API come piano B (vedi ``dataapi.py``).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser
import httpx

from ytkb.errors import TemporaryError

FEED_BASE = "https://www.youtube.com/feeds/videos.xml"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ytkb/0.1 (+feed reader)"


@dataclass(frozen=True)
class FeedEntry:
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    published: datetime | None
    link: str

    @property
    def is_short(self) -> bool:
        return "/shorts/" in self.link


class FeedUnavailable(TemporaryError):
    """Il feed non risponde (404/5xx intermittenti di YouTube, rete)."""


def channel_feed_url(channel_id: str) -> str:
    return f"{FEED_BASE}?channel_id={channel_id}"


def playlist_feed_url(playlist_id: str) -> str:
    return f"{FEED_BASE}?playlist_id={playlist_id}"


def _ts(struct) -> datetime | None:
    return datetime.fromtimestamp(calendar.timegm(struct), UTC) if struct else None


def parse_feed(content: bytes | str) -> list[FeedEntry]:
    parsed = feedparser.parse(content)
    feed_title = parsed.feed.get("title", "") if parsed.get("feed") else ""
    entries: list[FeedEntry] = []
    for e in parsed.entries:
        vid = e.get("yt_videoid") or (e.get("id", "").split(":")[-1] if e.get("id", "").startswith("yt:video:") else "")
        if not vid:
            continue
        entries.append(FeedEntry(
            video_id=vid,
            channel_id=e.get("yt_channelid", ""),
            channel_title=(e.get("author") or feed_title or ""),
            title=e.get("title", ""),
            published=_ts(e.get("published_parsed")),
            link=e.get("link", ""),
        ))
    return entries


def fetch_feed(url: str, client: httpx.Client) -> list[FeedEntry]:
    try:
        r = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    except httpx.HTTPError as exc:
        raise FeedUnavailable(f"feed non raggiungibile: {type(exc).__name__}") from exc
    if r.status_code != 200:
        raise FeedUnavailable(f"feed HTTP {r.status_code}")
    return parse_feed(r.content)
