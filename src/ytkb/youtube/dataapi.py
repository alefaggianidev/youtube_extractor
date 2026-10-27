"""YouTube Data API v3 con una semplice API key (niente OAuth, niente accesso al tuo account).

Costi di quota (10.000 unità gratuite al giorno): ``playlistItems.list`` 1 unità, ``channels.list`` 1 unità.
"""

from __future__ import annotations

import contextlib
from datetime import datetime

import httpx

from ytkb.errors import PermanentError, TemporaryError
from ytkb.utils.timeutil import from_iso
from ytkb.youtube.feeds import FeedEntry
from ytkb.youtube.urls import uploads_playlist_id

API = "https://www.googleapis.com/youtube/v3"


class DataApiError(TemporaryError):
    pass


class DataApi:
    def __init__(self, api_key: str, client: httpx.Client):
        self._key = api_key
        self._client = client

    def _get(self, endpoint: str, **params: str | int) -> dict:
        try:
            r = self._client.get(f"{API}/{endpoint}", params={**params, "key": self._key}, timeout=20)
        except httpx.HTTPError as exc:
            raise DataApiError(f"YouTube Data API non raggiungibile: {type(exc).__name__}") from exc
        if r.status_code == 200:
            return r.json()
        reason = ""
        with contextlib.suppress(ValueError, KeyError, IndexError, TypeError):
            reason = r.json()["error"]["errors"][0].get("reason", "")
        if r.status_code == 403 and reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise DataApiError("quota giornaliera della YouTube Data API esaurita")
        if r.status_code in (400, 403):
            raise PermanentError(f"YouTube Data API ha rifiutato la richiesta ({r.status_code} {reason}): "
                                 "controlla YOUTUBE_API_KEY")
        if r.status_code == 404:
            raise PermanentError(f"risorsa inesistente ({endpoint})")
        raise DataApiError(f"YouTube Data API HTTP {r.status_code}")

    def recent_uploads(self, channel_id: str, max_results: int = 10) -> list[FeedEntry]:
        data = self._get("playlistItems", part="snippet,contentDetails",
                         playlistId=uploads_playlist_id(channel_id), maxResults=max_results)
        out: list[FeedEntry] = []
        for item in data.get("items", []):
            cd, sn = item.get("contentDetails", {}), item.get("snippet", {})
            vid = cd.get("videoId") or sn.get("resourceId", {}).get("videoId")
            if not vid:
                continue
            published: datetime | None = from_iso(cd.get("videoPublishedAt") or sn.get("publishedAt"))
            out.append(FeedEntry(video_id=vid, channel_id=channel_id,
                                 channel_title=sn.get("videoOwnerChannelTitle") or sn.get("channelTitle", ""),
                                 title=sn.get("title", ""), published=published,
                                 link=f"https://www.youtube.com/watch?v={vid}"))
        return out

    def channel_by_handle(self, handle: str) -> tuple[str, str] | None:
        data = self._get("channels", part="snippet", forHandle=handle if handle.startswith("@") else f"@{handle}")
        items = data.get("items") or []
        if not items:
            return None
        return items[0]["id"], items[0].get("snippet", {}).get("title", "")

    def channel_title(self, channel_id: str) -> str | None:
        data = self._get("channels", part="snippet", id=channel_id)
        items = data.get("items") or []
        return items[0].get("snippet", {}).get("title", "") if items else None
