"""``ytkb run``: il demone che gira 24/7 (controllo canali + lavorazione della coda + bot Telegram)."""

from __future__ import annotations

import contextlib
import logging
import signal
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from ytkb.config import Settings
from ytkb.db import Database
from ytkb.utils.timeutil import utcnow

log = logging.getLogger(__name__)


class Daemon:
    def __init__(self, settings: Settings, db: Database, *, pipeline, monitor, bot=None,
                 clock: Callable[[], datetime] = utcnow, idle_sleep_s: float = 20.0):
        self.settings = settings
        self.db = db
        self.pipeline = pipeline
        self.monitor = monitor
        self.bot = bot
        self.clock = clock
        self.idle_sleep_s = idle_sleep_s
        self.stop_event = threading.Event()
        self._next_poll: datetime | None = None
        self._next_release: datetime | None = None
        self._bot_thread: threading.Thread | None = None

    # --- un giro del ciclo (testabile) ------------------------------------------------
    def tick(self) -> bool:
        """Esegue un passo. Restituisce True se ha lavorato un video (quindi conviene non dormire)."""
        now = self.clock()
        self.db.kv_set("daemon_heartbeat", now.isoformat(timespec="seconds"))
        if self._next_release is None or now >= self._next_release:
            self.db.release_stale(self.settings.worker.stale_processing_minutes, now=now)
            self._next_release = now + timedelta(minutes=10)
        if self.monitor is not None and (self._next_poll is None or now >= self._next_poll):
            try:
                self.monitor.poll(now=now)
            except Exception:  # noqa: BLE001 - un errore nel polling non deve fermare il demone
                log.exception("Errore durante il controllo dei canali")
            self._next_poll = now + timedelta(minutes=self.settings.monitor.poll_interval_minutes)
        try:
            return self.pipeline.run_next() is not None
        except Exception:  # noqa: BLE001
            log.exception("Errore del worker")
            return False

    # --- ciclo principale -------------------------------------------------------------
    def _install_signals(self) -> None:
        def handler(signum, _frame):
            log.info("Ricevuto segnale %s: chiusura in corso…", signal.Signals(signum).name)
            self.stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(ValueError):  # ValueError se non siamo nel thread principale (es. test)
                signal.signal(sig, handler)

    def start_bot(self) -> None:
        if self.bot is None:
            return
        self._bot_thread = threading.Thread(target=self.bot.run, args=(self.stop_event,), name="ytkb-telegram",
                                            daemon=True)
        self._bot_thread.start()
        log.info("Bot Telegram avviato")

    def run_forever(self) -> None:
        self._install_signals()
        released = self.db.release_stale(self.settings.worker.stale_processing_minutes, now=self.clock())
        if released:
            log.info("Rimessi in coda %d video rimasti in lavorazione da un avvio precedente", released)
        log.info("Demone avviato: controllo canali ogni %.0f minuti", self.settings.monitor.poll_interval_minutes)
        self.start_bot()
        while not self.stop_event.is_set():
            worked = self.tick()
            if not worked:
                self.stop_event.wait(self.idle_sleep_s)
        log.info("Demone fermato")
