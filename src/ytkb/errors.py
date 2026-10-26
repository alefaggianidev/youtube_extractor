"""Errori tipizzati della pipeline.

La pipeline decide cosa fare di un video guardando il *tipo* di errore:

- ``NotReadyError``   -> YouTube non è ancora pronto (premiere, live, sottotitoli): stato ``waiting``.
- ``TemporaryError``  -> errore passeggero (rete, 429, 5xx): si riprova con backoff.
- ``BlockedError``    -> YouTube ci sta bloccando (bot-check, IP): si riprova, ma va segnalato.
- ``PermanentError``  -> non ha senso riprovare (video privato, rimosso): stato ``failed``.
- ``SkipError``       -> scelta voluta di non processare (Short, filtri): stato ``skipped``.
"""

from __future__ import annotations


class YtkbError(Exception):
    """Base di tutti gli errori del progetto."""


class NotReadyError(YtkbError):
    def __init__(self, message: str, retry_after_minutes: float | None = None):
        super().__init__(message)
        self.retry_after_minutes = retry_after_minutes


class TemporaryError(YtkbError):
    """Errore passeggero: riprovare più tardi."""


class BlockedError(TemporaryError):
    """YouTube (o un altro servizio) sta bloccando le nostre richieste."""


class PermanentError(YtkbError):
    """Errore definitivo: riprovare non serve."""


class SkipError(YtkbError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ConfigError(YtkbError):
    """Configurazione mancante o non valida."""


class BudgetExceededError(NotReadyError):
    """Budget giornaliero LLM superato: il video aspetta il giorno dopo."""
