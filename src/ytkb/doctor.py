"""``ytkb doctor``: controlla che l'ambiente abbia tutto ciò che serve, con consigli pratici."""

from __future__ import annotations

import importlib.metadata as md
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ytkb.config import Settings
from ytkb.db import open_db
from ytkb.youtube.ytdlp import find_deno


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""
    optional: bool = False


def _version(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def _run_version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"errore: {exc}"


def local_checks(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    py = sys.version_info
    checks.append(Check("Python", py >= (3, 11), f"{py.major}.{py.minor}.{py.micro}", "Serve Python 3.11 o superiore"))
    checks.append(Check(
        "Configurazione", True,
        str(settings.source_file) if settings.source_file else "nessun settings.yaml: uso i default",
        "" if settings.source_file else "Esegui `ytkb init` per creare config/settings.yaml",
    ))
    try:
        settings.ensure_dirs()
        db = open_db(settings.db_path)
        db.close()
        checks.append(Check("Cartelle dati e database", True, str(settings.data_dir)))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("Cartelle dati e database", False, str(exc), "Controlla permessi e percorso paths.data_dir"))

    ffmpeg = shutil.which("ffmpeg")
    checks.append(Check("ffmpeg", bool(ffmpeg), _run_version([ffmpeg, "-version"]) if ffmpeg else "non trovato",
                        "RHEL 9: usa il container, oppure installa ffmpeg da RPM Fusion"))
    deno = find_deno(settings)
    checks.append(Check("Deno (per yt-dlp)", bool(deno), _run_version([deno, "--version"]) if deno else "non trovato",
                        "Installa le dipendenze con `uv sync` (il pacchetto 'deno' porta il binario)"))
    ytdlp = _version("yt-dlp")
    ejs = _version("yt-dlp-ejs")
    checks.append(Check("yt-dlp", bool(ytdlp), f"{ytdlp or 'mancante'} (ejs {ejs or 'mancante'})",
                        "Aggiorna spesso: `uv lock --upgrade-package yt-dlp && uv sync`"))
    checks.append(Check("youtube-transcript-api", bool(_version("youtube-transcript-api")),
                        _version("youtube-transcript-api") or "mancante"))
    checks.append(Check("google-genai", bool(_version("google-genai")), _version("google-genai") or "mancante"))

    s = settings.secrets
    needs_gemini = settings.llm.provider == "gemini"
    checks.append(Check("GEMINI_API_KEY", bool(s.gemini_api_key) or not needs_gemini,
                        "presente" if s.gemini_api_key else ("non necessaria (provider fake)" if not needs_gemini else "mancante"),
                        "Crea la chiave su https://aistudio.google.com/apikey e mettila in .env"))
    checks.append(Check("YOUTUBE_API_KEY", bool(s.youtube_api_key), "presente" if s.youtube_api_key else "assente",
                        "Facoltativa: piano B se l'RSS non risponde", optional=True))
    tg_needed = settings.telegram.enabled
    checks.append(Check("Telegram", (bool(s.telegram_bot_token) and bool(settings.telegram.allowed_chat_ids)) or not tg_needed,
                        "disattivato" if not tg_needed else (
                            "token e chat autorizzate presenti" if s.telegram_bot_token and settings.telegram.allowed_chat_ids
                            else "manca il token o allowed_chat_ids"),
                        "Imposta TELEGRAM_BOT_TOKEN in .env e telegram.allowed_chat_ids", optional=not tg_needed))
    return checks


def _http_probe(name: str, url: str, ok_codes: Callable[[int], bool], hint: str, client: httpx.Client,
                optional: bool = False) -> Check:
    try:
        r = client.get(url)
        return Check(name, ok_codes(r.status_code), f"HTTP {r.status_code}", hint, optional)
    except httpx.HTTPError as exc:
        return Check(name, False, f"{type(exc).__name__}: {exc}", hint, optional)


def network_checks(settings: Settings, client: httpx.Client | None = None) -> list[Check]:
    own = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True,
                                    headers={"User-Agent": "Mozilla/5.0 (ytkb doctor)"})
    try:
        return [
            _http_probe("Rete → feed RSS YouTube",
                        "https://www.youtube.com/feeds/videos.xml?channel_id=UCBR8-60-B28hp2BmDPdntcQ",
                        lambda c: c == 200,
                        "404 a intermittenza è un problema noto di YouTube: riprova più tardi o imposta YOUTUBE_API_KEY",
                        client),
            _http_probe("Rete → Gemini API", "https://generativelanguage.googleapis.com/",
                        lambda c: c < 500, "La VM deve poter raggiungere generativelanguage.googleapis.com", client),
            _http_probe("Rete → Telegram", "https://api.telegram.org/", lambda c: c < 500,
                        "Serve solo se usi il bot", client, optional=not settings.telegram.enabled),
        ]
    finally:
        if own:
            client.close()
