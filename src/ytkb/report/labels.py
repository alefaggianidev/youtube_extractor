"""Etichette in italiano per i valori degli schemi."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

VIDEO_TYPE = {
    "OPERATIONAL_TRADING": "Analisi operativa",
    "EDUCATIONAL_THEORY": "Formazione / teoria",
    "MACRO_ANALYSIS": "Analisi macro",
    "HYBRID": "Misto (operativo + teoria)",
    "OTHER": "Altro",
}
BIAS = {
    "BULLISH": ("🟢", "Rialzista"),
    "BEARISH": ("🔴", "Ribassista"),
    "NEUTRAL": ("⚪", "Neutrale"),
    "MIXED": ("🟡", "Misto"),
}
LEVEL_KIND = {
    "SUPPORT": "Supporto",
    "RESISTANCE": "Resistenza",
    "TARGET": "Obiettivo",
    "STOP": "Stop",
    "ENTRY": "Ingresso",
    "PIVOT": "Pivot",
    "OTHER": "Livello",
}
TRIGGER = {
    "PRICE_CHART": "Grafico di prezzo",
    "EDUCATIONAL_SLIDE": "Slide didattica",
    "INDICATOR_SETTINGS": "Impostazioni indicatore",
    "DATA_TABLE": "Tabella dati",
    "OTHER": "Schermata",
}
CONFIDENCE = {"LOW": "bassa", "MEDIUM": "media", "HIGH": "alta"}
PROVENANCE = {
    "spoken": ("🗣️", "detto a voce"),
    "chart": ("👁️", "letto dal grafico"),
    "unverified": ("🤖", "non verificato"),
}
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre"]


def date_it(value: date | datetime | None, tz_name: str = "Europe/Rome", with_time: bool = False) -> str:
    if value is None:
        return "data sconosciuta"
    if isinstance(value, datetime):
        local = value.astimezone(ZoneInfo(tz_name))
        text = f"{local.day} {MONTHS[local.month - 1]} {local.year}"
        return f"{text}, {local:%H:%M}" if with_time else text
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def stars(score: int) -> str:
    score = max(0, min(5, int(score)))
    return "★" * score + "☆" * (5 - score)
