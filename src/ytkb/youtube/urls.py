"""Riconoscimento dei link YouTube e costruzione dei link "al secondo esatto"."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+|(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^\s<>\"']+")

_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com",
             "www.youtube-nocookie.com"}


def extract_video_id(text: str) -> str | None:
    """Estrae l'ID (11 caratteri) da un link YouTube o da un ID nudo.

    >>> extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=42")
    'dQw4w9WgXcQ'
    >>> extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1")
    'dQw4w9WgXcQ'
    >>> extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    'dQw4w9WgXcQ'
    """
    if not text:
        return None
    text = text.strip()
    if VIDEO_ID_RE.match(text):
        return text
    if not re.match(r"^[a-z]+://", text):
        text = "https://" + text
    try:
        u = urlparse(text)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    candidate: str | None = None
    if host == "youtu.be":
        candidate = u.path.lstrip("/").split("/")[0]
    elif host in _YT_HOSTS:
        qs = parse_qs(u.query)
        if u.path == "/watch" and qs.get("v"):
            candidate = qs["v"][0]
        else:
            m = re.match(r"^/(?:shorts|live|embed|v|e)/([^/?#]+)", u.path)
            if m:
                candidate = m.group(1)
            elif qs.get("v"):
                candidate = qs["v"][0]
    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def find_video_ids(text: str) -> list[str]:
    """Tutti gli ID video presenti in un testo (es. un messaggio Telegram), senza duplicati."""
    out: list[str] = []
    for match in _URL_IN_TEXT.findall(text or ""):
        vid = extract_video_id(match.rstrip(").,;!"))
        if vid and vid not in out:
            out.append(vid)
    return out


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def timestamp_url(video_id: str, seconds: float) -> str:
    """Link che apre il video al secondo indicato."""
    return f"https://youtu.be/{video_id}?t={max(0, int(seconds))}"


def parse_channel_ref(text: str) -> tuple[str, str] | None:
    """Riconosce un riferimento a un canale.

    Restituisce ``("id", "UC...")``, ``("handle", "@nome")`` oppure ``("url", link)`` per i vecchi /c/ e /user/.

    >>> parse_channel_ref("@TradingFacile")
    ('handle', '@TradingFacile')
    >>> parse_channel_ref("https://www.youtube.com/channel/UCBR8-60-B28hp2BmDPdntcQ")
    ('id', 'UCBR8-60-B28hp2BmDPdntcQ')
    """
    text = (text or "").strip()
    if not text:
        return None
    if CHANNEL_ID_RE.match(text):
        return ("id", text)
    if re.match(r"^@[\w.\-]{2,}$", text):
        return ("handle", text)
    if not re.match(r"^[a-z]+://", text):
        text = "https://" + text
    try:
        u = urlparse(text)
    except ValueError:
        return None
    if (u.hostname or "").lower() not in _YT_HOSTS:
        return None
    parts = [p for p in u.path.split("/") if p]
    if not parts:
        return None
    if parts[0] == "channel" and len(parts) > 1 and CHANNEL_ID_RE.match(parts[1]):
        return ("id", parts[1])
    if parts[0].startswith("@"):
        return ("handle", parts[0])
    if parts[0] in ("c", "user") and len(parts) > 1:
        return ("url", f"https://www.youtube.com/{parts[0]}/{parts[1]}")
    return None


def uploads_playlist_id(channel_id: str) -> str:
    """La playlist "caricamenti" di un canale: stesso ID con prefisso UU invece di UC."""
    return "UU" + channel_id[2:]
