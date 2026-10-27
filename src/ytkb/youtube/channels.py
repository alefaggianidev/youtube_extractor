"""Canali seguiti: ``config/channels.yaml`` è la fonte di verità (leggibile e modificabile a mano).

Si possono aggiungere con ``ytkb channels add @nome`` o importare dalle iscrizioni (Google Takeout, ``subscriptions.csv``).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ytkb.config import FilterSettings, Settings
from ytkb.db import Database
from ytkb.errors import ConfigError, PermanentError
from ytkb.youtube.urls import CHANNEL_ID_RE, parse_channel_ref

log = logging.getLogger(__name__)

HEADER = """# =============================================================================
#  Canali seguiti da yt-finance-kb  (file gestito anche da `ytkb channels ...`)
#  Campi: id (UC..., obbligatorio), name, enabled, filters (facoltativo: come in settings.yaml)
# =============================================================================
"""


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = ""
    enabled: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not CHANNEL_ID_RE.match(self.id):
            raise ValueError(f"channel id non valido: {self.id!r} (deve iniziare con UC e avere 24 caratteri)")
        if self.filters:
            FilterSettings().merged(self.filters)  # valida le chiavi dei filtri


def load_channels(path: Path) -> list[ChannelConfig]:
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Errore di sintassi YAML in {path}: {exc}") from exc
    items = raw.get("channels") or [] if isinstance(raw, dict) else []
    out: list[ChannelConfig] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        try:
            ch = ChannelConfig.model_validate(item)
        except (ValidationError, ValueError) as exc:
            raise ConfigError(f"{path}: canale n. {i + 1} non valido: {exc}") from exc
        if ch.id not in seen:
            seen.add(ch.id)
            out.append(ch)
    return out


def _entry_yaml(ch: ChannelConfig) -> str:
    data: dict[str, Any] = {"id": ch.id, "name": ch.name, "enabled": ch.enabled}
    if ch.filters:
        data["filters"] = ch.filters
    text = yaml.safe_dump([data], allow_unicode=True, sort_keys=False, width=1000)
    return "".join(f"  {line}\n" for line in text.splitlines())


def append_channels(path: Path, new: list[ChannelConfig]) -> int:
    """Aggiunge canali in fondo al file, **conservando i commenti** esistenti. Restituisce quanti ne ha aggiunti."""
    existing = {c.id for c in load_channels(path)}
    to_add = [c for c in new if c.id not in existing]
    if not to_add:
        return 0
    text = path.read_text(encoding="utf-8") if path.exists() else HEADER + "channels:\n"
    if re.search(r"^channels:\s*\[\s*\]\s*$", text, flags=re.MULTILINE):
        text = re.sub(r"^channels:\s*\[\s*\]\s*$", "channels:", text, flags=re.MULTILINE)
    if not re.search(r"^channels:", text, flags=re.MULTILINE):
        text = text.rstrip("\n") + "\nchannels:\n"
    if not text.endswith("\n"):
        text += "\n"
    text += "".join(_entry_yaml(c) for c in to_add)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    load_channels(path)  # verifica che il risultato sia valido
    return len(to_add)


def rewrite_channels(path: Path, channels: list[ChannelConfig]) -> None:
    """Riscrive il file (usato per abilitare/disabilitare/rimuovere: i commenti dentro le voci si perdono)."""
    body = "channels:\n" + "".join(_entry_yaml(c) for c in channels) if channels else "channels: []\n"
    path.write_text(HEADER + body, encoding="utf-8")


def parse_takeout_csv(content: str) -> list[ChannelConfig]:
    """Legge ``subscriptions.csv`` di Google Takeout (colonne: ID canale, URL canale, titolo; intestazioni in
    qualsiasi lingua)."""
    out: list[ChannelConfig] = []
    for row in csv.reader(io.StringIO(content.lstrip("﻿"))):
        if not row or not CHANNEL_ID_RE.match(row[0].strip()):
            continue  # intestazione o riga vuota
        title = row[2].strip() if len(row) > 2 else ""
        out.append(ChannelConfig(id=row[0].strip(), name=title))
    return out


def sync_to_db(channels: list[ChannelConfig], db: Database) -> None:
    yaml_ids = {c.id for c in channels}
    for c in channels:
        db.upsert_channel(c.id, title=c.name, enabled=c.enabled)
    for row in db.list_channels():
        if row.channel_id not in yaml_ids and row.enabled:
            db.upsert_channel(row.channel_id, enabled=False)


def channel_filter_lookup(settings: Settings) -> Callable[[str], dict[str, Any] | None]:
    """Funzione channel_id -> filtri specifici del canale (rilegge il file solo se è cambiato)."""
    cache: dict[str, Any] = {"mtime": None, "filters": {}}

    def lookup(channel_id: str) -> dict[str, Any] | None:
        path = settings.channels_file
        mtime = path.stat().st_mtime if path.exists() else None
        if mtime != cache["mtime"]:
            try:
                cache["filters"] = {c.id: c.filters for c in load_channels(path) if c.filters}
            except ConfigError as exc:
                log.warning("Filtri per canale ignorati: %s", exc)
                cache["filters"] = {}
            cache["mtime"] = mtime
        return cache["filters"].get(channel_id)

    return lookup


Resolver = Callable[[str], tuple[str, str] | None]


def resolve_channel_ref(ref: str, by_handle: Resolver, by_url: Resolver | None = None) -> tuple[str, str]:
    """``@nome`` / link / ID → (channel_id, titolo). Usa la Data API o yt-dlp (iniettati)."""
    parsed = parse_channel_ref(ref)
    if parsed is None:
        raise PermanentError(f"Riferimento al canale non riconosciuto: {ref!r} (usa @nome, un link o l'ID UC...)")
    kind, value = parsed
    if kind == "id":
        return value, ""
    resolver = by_handle if kind == "handle" else (by_url or by_handle)
    found = resolver(value)
    if not found:
        raise PermanentError(f"Canale non trovato: {ref}")
    return found


def ytdlp_resolver(settings: Settings) -> Resolver:
    """Risolve @nome o un vecchio link /c/ con yt-dlp (senza API key)."""

    def resolve(value: str) -> tuple[str, str] | None:
        import yt_dlp

        from ytkb.youtube.ytdlp import base_options, classify_error

        url = value if value.startswith("http") else f"https://www.youtube.com/{value}"
        opts = base_options(settings) | {"extract_flat": True, "playlist_items": "0", "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # noqa: BLE001
            raise classify_error(exc) from exc
        cid = (info or {}).get("channel_id") or (info or {}).get("id")
        if not cid or not CHANNEL_ID_RE.match(cid):
            return None
        return cid, (info.get("channel") or info.get("uploader") or info.get("title") or "")

    return resolve
