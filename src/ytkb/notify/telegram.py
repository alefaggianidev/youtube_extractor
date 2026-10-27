"""Telegram con chiamate HTTP dirette alla Bot API (D-010).

- **Notifiche**: riassunto breve + report HTML allegato quando un video è pronto (o un avviso se fallisce).
- **Bot**: mandi un link YouTube nella chat → il video va in coda con priorità alta; ``/stato`` mostra la coda.
- **Sicurezza**: solo i ``chat_id`` in ``telegram.allowed_chat_ids`` possono usarlo; il token non finisce mai nei log.
- Nessuna porta aperta sulla VM: si usa il *long polling* (è la VM a chiamare Telegram).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

import httpx

from ytkb.config import Settings
from ytkb.db import Database
from ytkb.errors import ConfigError, PermanentError, TemporaryError
from ytkb.models import VideoStatus
from ytkb.youtube.urls import find_video_ids

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MAX_DOCUMENT_BYTES = 49 * 1024 * 1024  # limite dei bot: 50 MB


class TelegramClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN mancante nel file .env")
        self._token = token
        self._http = client or httpx.Client(timeout=httpx.Timeout(70.0, connect=15.0))

    def call(self, method: str, *, files: dict[str, Any] | None = None, http_timeout: float | None = None,
             **params: Any) -> Any:
        url = f"{API_BASE}/bot{self._token}/{method}"
        data = {k: v for k, v in params.items() if v is not None}
        if files:  # multipart: i valori devono essere stringhe
            data = {k: str(v) for k, v in data.items()}
        for attempt in range(3):
            try:
                if files:
                    r = self._http.post(url, data=data, files=files, timeout=http_timeout or 120)
                else:
                    r = self._http.post(url, json=data, timeout=http_timeout or 30)
            except httpx.HTTPError as exc:  # il messaggio di httpx contiene l'URL (con il token): non lo propaghiamo
                raise TemporaryError(f"Telegram non raggiungibile ({type(exc).__name__})") from None
            try:
                body = r.json()
            except ValueError:
                body = {}
            if r.status_code == 200 and body.get("ok"):
                return body.get("result")
            if r.status_code == 429 and attempt < 2:
                wait = float((body.get("parameters") or {}).get("retry_after", 2))
                time.sleep(min(wait, 30))
                continue
            desc = body.get("description", f"HTTP {r.status_code}")
            if r.status_code in (401, 404):
                raise ConfigError("Token Telegram non valido (controlla TELEGRAM_BOT_TOKEN)")
            if r.status_code >= 500:
                raise TemporaryError(f"Telegram: {desc}")
            raise PermanentError(f"Telegram: {desc}")
        raise TemporaryError("Telegram: troppe richieste")

    def send_message(self, chat_id: int | str, text: str, html: bool = True) -> Any:
        try:
            return self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML" if html else None,
                             disable_web_page_preview=True)
        except PermanentError as exc:
            if html and "parse" in str(exc).lower():  # HTML non accettato: riprova come testo semplice
                return self.call("sendMessage", chat_id=chat_id, text=_strip_tags(text),
                                 disable_web_page_preview=True)
            raise

    def send_document(self, chat_id: int | str, path: Path, caption: str = "") -> Any:
        with open(path, "rb") as fh:
            return self.call("sendDocument", chat_id=chat_id, caption=caption[:1000] or None,
                             parse_mode="HTML" if caption else None,
                             files={"document": (path.name, fh, "text/html")})

    def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict[str, Any]]:
        """Long polling: Telegram tiene aperta la richiesta fino a ``timeout`` secondi se non ci sono messaggi."""
        return self.call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"],
                         http_timeout=timeout + 15) or []


def _strip_tags(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", text)


def _e(text: object) -> str:
    return escape(str(text or ""), quote=False)


# ------------------------------------------------------------------------------------------
class TelegramNotifier:
    def __init__(self, client: TelegramClient, allowed_chat_ids: list[int], send_html_report: bool = True):
        self.client = client
        self.allowed = [int(c) for c in allowed_chat_ids]
        self.send_html_report = send_html_report

    @classmethod
    def from_settings(cls, settings: Settings) -> TelegramNotifier:
        token = settings.secrets.reveal(settings.secrets.telegram_bot_token)
        return cls(TelegramClient(token), settings.telegram.allowed_chat_ids, settings.telegram.send_html_report)

    def _targets(self, requested_by: str | None) -> list[int]:
        if requested_by:
            try:
                chat = int(requested_by)
                if chat in self.allowed:
                    return [chat]
            except ValueError:
                pass
        return list(self.allowed)

    def video_done(self, *, video_id: str, title: str, channel: str, summary_html: str, report_html: Any,
                   requested_by: str | None) -> None:
        path = Path(report_html) if report_html else None
        for chat in self._targets(requested_by):
            self.client.send_message(chat, summary_html)
            if self.send_html_report and path and path.exists():
                if path.stat().st_size <= MAX_DOCUMENT_BYTES:
                    self.client.send_document(chat, path, caption=f"📎 Report completo: <b>{_e(title)}</b>")
                else:
                    self.client.send_message(chat, "📎 Il report HTML supera i 50 MB: lo trovi nell'archivio.")

    def video_failed(self, *, video_id: str, title: str, error: str, requested_by: str | None) -> None:
        text = (f"❌ <b>Analisi non riuscita</b>: {_e(title)}\n<code>{_e(error[:600])}</code>\n"
                f"Per riprovare: <code>ytkb retry {video_id}</code>")
        for chat in self._targets(requested_by):
            self.client.send_message(chat, text)


# ------------------------------------------------------------------------------------------
HELP = ("Mandami uno o più link YouTube e li analizzo, poi ti invio il report.\n"
        "Comandi: /stato (coda e ultimi video), /aiuto")


class TelegramBot:
    """Riceve i messaggi (long polling) e mette in coda i link YouTube delle chat autorizzate."""

    OFFSET_KEY = "telegram_offset"

    def __init__(self, client: TelegramClient, db: Database, allowed_chat_ids: list[int],
                 resend_report: Callable[[int, str], bool] | None = None):
        self.client = client
        self.db = db
        self.allowed = {int(c) for c in allowed_chat_ids}
        self.resend_report = resend_report

    @classmethod
    def from_settings(cls, settings: Settings, db: Database) -> TelegramBot:
        token = settings.secrets.reveal(settings.secrets.telegram_bot_token)
        client = TelegramClient(token)
        notifier = TelegramNotifier(client, settings.telegram.allowed_chat_ids, settings.telegram.send_html_report)

        def resend(chat_id: int, video_id: str) -> bool:
            row = db.get_video(video_id)
            if not row or not row.archive_dir:
                return False
            path = Path(row.archive_dir) / "report.html"
            if not path.exists():
                return False
            notifier.client.send_document(chat_id, path, caption=f"📎 Report: <b>{_e(row.title)}</b>")
            return True

        return cls(client, db, settings.telegram.allowed_chat_ids, resend_report=resend)

    # --- gestione di un singolo messaggio (testabile) -----------------------------------
    def handle_update(self, update: dict[str, Any]) -> None:
        msg = update.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if chat_id is None:
            return
        if chat_id not in self.allowed:
            log.warning("Messaggio Telegram da chat non autorizzata %s", chat_id)
            self.client.send_message(chat_id, f"⛔ Chat non autorizzata. Il tuo chat_id è <code>{chat_id}</code>: "
                                              "aggiungilo a <code>telegram.allowed_chat_ids</code> nella "
                                              "configurazione di ytkb.")
            return
        command = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""
        if command in ("/start", "/aiuto", "/help"):
            self.client.send_message(chat_id, f"👋 Ciao! Il tuo chat_id è <code>{chat_id}</code>.\n{_e(HELP)}")
            return
        if command in ("/stato", "/status"):
            self.client.send_message(chat_id, self._status_text())
            return
        video_ids = find_video_ids(text)
        if not video_ids:
            self.client.send_message(chat_id, _e(HELP))
            return
        replies = [self._enqueue(chat_id, vid) for vid in video_ids]
        self.client.send_message(chat_id, "\n".join(r for r in replies if r))

    def _enqueue(self, chat_id: int, vid: str) -> str:
        if self.db.add_video(vid, source="telegram", priority=10, requested_by=str(chat_id)):
            return f"✅ In coda: <code>{vid}</code>. Ti scrivo quando il report è pronto."
        row = self.db.get_video(vid)
        if row is None:
            return ""
        if row.status == VideoStatus.DONE:
            if self.resend_report and self.resend_report(chat_id, vid):
                return f"♻️ Già analizzato: <b>{_e(row.title)}</b> (report qui sopra)."
            return f"♻️ Già analizzato: <b>{_e(row.title)}</b>."
        if row.status in (VideoStatus.FAILED, VideoStatus.SKIPPED):
            self.db.requeue(vid, priority=10, requested_by=str(chat_id))
            return f"🔁 Rimesso in coda: <b>{_e(row.title or vid)}</b>."
        self.db.update_video(vid, priority=10, requested_by=str(chat_id))
        return f"⏳ Già in coda: <b>{_e(row.title or vid)}</b> (stato: {row.status})."

    def _status_text(self) -> str:
        counts = self.db.count_by_status()
        head = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "nessun video"
        lines = [f"📊 <b>Stato</b>: {_e(head)}"]
        for r in self.db.list_videos(limit=5):
            lines.append(f"• {_e(r.status)} — {_e((r.title or r.video_id)[:60])}")
        return "\n".join(lines)

    # --- ciclo di ascolto ---------------------------------------------------------------
    def poll_once(self, timeout: int = 50) -> int:
        offset_raw = self.db.kv_get(self.OFFSET_KEY)
        offset = int(offset_raw) if offset_raw else None
        updates = self.client.get_updates(offset, timeout=timeout)
        for upd in updates:
            try:
                self.handle_update(upd)
            except Exception as exc:  # noqa: BLE001 - un messaggio "strano" non deve fermare il bot
                log.warning("Messaggio Telegram non gestito: %s", exc)
            finally:
                self.db.kv_set(self.OFFSET_KEY, str(int(upd["update_id"]) + 1))
        return len(updates)

    def run(self, stop_event: threading.Event) -> None:
        backoff = 5.0
        while not stop_event.is_set():
            try:
                self.poll_once()
                backoff = 5.0
            except ConfigError as exc:
                log.error("Bot Telegram fermato: %s", exc)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("Bot Telegram: %s (riprovo tra %.0f s)", exc, backoff)
                stop_event.wait(backoff)
                backoff = min(backoff * 2, 300)
