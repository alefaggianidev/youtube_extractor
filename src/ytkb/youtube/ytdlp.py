"""Opzioni comuni per yt-dlp e classificazione dei suoi errori.

yt-dlp per YouTube richiede un runtime JavaScript (Deno, D-013): qui lo cerchiamo e lo passiamo in modo esplicito.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from ytkb.config import Settings
from ytkb.errors import BlockedError, NotReadyError, PermanentError, TemporaryError, YtkbError

log = logging.getLogger(__name__)


def find_deno(settings: Settings | None = None) -> str | None:
    """Percorso dell'eseguibile Deno: configurazione → PATH → stesso ambiente Python (pacchetto ``deno``)."""
    if settings and settings.ytdlp.deno_path:
        p = Path(settings.ytdlp.deno_path).expanduser()
        return str(p) if p.exists() else None
    found = shutil.which("deno")
    if found:
        return found
    for name in ("deno", "deno.exe"):
        candidate = Path(sys.executable).parent / name
        if candidate.exists():
            return str(candidate)
    try:  # il pacchetto PyPI "deno" espone il percorso del binario
        import deno  # type: ignore[import-not-found]

        for attr in ("find_deno_bin", "get_deno_path"):
            fn = getattr(deno, attr, None)
            if callable(fn):
                path = fn()
                if path and Path(path).exists():
                    return str(path)
    except Exception:  # noqa: BLE001 - il pacchetto è opzionale nella ricerca
        pass
    return None


class _YtdlpLogger:
    """Inoltra i messaggi di yt-dlp al logging standard (yt-dlp è molto loquace: debug → DEBUG)."""

    def __init__(self, logger: logging.Logger):
        self._log = logger

    def debug(self, msg: str) -> None:
        self._log.debug(msg)

    def info(self, msg: str) -> None:
        self._log.debug(msg)

    def warning(self, msg: str) -> None:
        self._log.info("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        self._log.debug("yt-dlp: %s", msg)  # l'errore viene riportato (ripulito) da chi chiama yt-dlp


def base_options(settings: Settings) -> dict[str, Any]:
    """Opzioni yt-dlp comuni a metadati, sottotitoli e sezioni video."""
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "logger": _YtdlpLogger(logging.getLogger("ytkb.ytdlp")),
        "socket_timeout": 30,
        "retries": 3,
        "extractor_retries": 2,
        "sleep_interval_requests": settings.ytdlp.sleep_requests_s or None,
        "noplaylist": True,
        "cachedir": str(settings.data_dir / "cache" / "yt-dlp"),
    }
    deno = find_deno(settings)
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    else:
        log.warning("Deno non trovato: YouTube funzionerà in modo ridotto (installa il pacchetto 'deno').")
    if settings.ytdlp.cookies_file:
        opts["cookiefile"] = str(Path(settings.ytdlp.cookies_file).expanduser())
    proxy = settings.secrets.reveal(settings.secrets.ytkb_proxy)
    if proxy:
        opts["proxy"] = proxy
    if settings.ytdlp.extractor_args:
        opts["extractor_args"] = settings.ytdlp.extractor_args
    return opts


# Frasi tipiche dei messaggi di errore di yt-dlp/YouTube → tipo di errore.
_NOT_READY = ("premieres in", "this live event will begin", "will begin in", "is upcoming", "live event will start",
              "this live stream recording is not available", "processing this video")
_BLOCKED = ("sign in to confirm you", "confirm you're not a bot", "confirm you’re not a bot", "http error 429",
            "too many requests", "po token", "potoken", "requested format is not available")
_PERMANENT = ("private video", "video unavailable", "this video has been removed", "members-only",
              "join this channel", "available to this channel's members", "has been terminated",
              "account associated with this video has been", "not available in your country",
              "copyright", "inappropriate for some users", "sign in to confirm your age", "age-restricted")


def clean_message(msg: str) -> str:
    """Toglie da un errore di yt-dlp le parti ripetitive ("please report this issue…", "caused by…")."""
    msg = re.sub(r"^\s*ERROR:\s*", "", msg or "")
    msg = re.sub(r";?\s*please report this issue on.*$", "", msg, flags=re.IGNORECASE | re.DOTALL)
    msg = re.sub(r"\s*\(caused by .*$", "", msg, flags=re.DOTALL)
    return " ".join(msg.split())[:500]


def classify_error(exc: BaseException) -> YtkbError:
    """Converte un errore di yt-dlp in un errore tipizzato del progetto (con messaggio ripulito)."""
    if isinstance(exc, YtkbError):
        return exc
    msg = clean_message(str(exc))
    low = msg.lower()
    if any(p in low for p in _NOT_READY):
        return NotReadyError(msg, retry_after_minutes=30)
    if any(p in low for p in _BLOCKED):
        return BlockedError(msg)
    if any(p in low for p in _PERMANENT):
        return PermanentError(msg)
    return TemporaryError(msg)
