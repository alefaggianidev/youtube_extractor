"""Configurazione del logging, con mascheramento dei segreti."""

from __future__ import annotations

import logging
import sys


class RedactSecretsFilter(logging.Filter):
    """Sostituisce i segreti noti con ``***`` in ogni messaggio di log."""

    def __init__(self, secrets: list[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s and len(s) >= 6]

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            msg = record.getMessage()
            for secret in self._secrets:
                if secret in msg:
                    msg = msg.replace(secret, "***")
            record.msg, record.args = msg, None
        return True


class _CurrentStderrHandler(logging.StreamHandler):
    """Scrive sempre sul ``sys.stderr`` corrente (utile se lo stream viene sostituito, es. nei test)."""

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


def setup_logging(level: str = "INFO", secrets: list[str] | None = None) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = _CurrentStderrHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    handler.addFilter(RedactSecretsFilter(secrets or []))
    root.addHandler(handler)
    root.setLevel(level.upper())
    # librerie molto loquaci
    for noisy in ("httpx", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
