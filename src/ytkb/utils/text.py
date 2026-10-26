"""Testo: nomi di file sicuri, formattazione di tempi e numeri, confronto "tollerante"."""

from __future__ import annotations

import math
import re
import unicodedata

# Caratteri vietati nei nomi di file Windows + caratteri che danno fastidio a Markdown/Obsidian/shell.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f#%&{}$!\'@+`=\[\]^~;,]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_DROP_CATEGORIES = {"So", "Sk", "Cf", "Co", "Cn", "Cs"}  # emoji, simboli, caratteri di formato


def sanitize_filename(name: str, max_len: int = 80, fallback: str = "senza_titolo") -> str:
    """Rende ``name`` utilizzabile come nome di file/cartella su Windows, Linux e Obsidian.

    >>> sanitize_filename('🔥 BTC: "settimana" decisiva? | Parte 2/3')
    'BTC_settimana_decisiva_Parte_2_3'
    """
    s = unicodedata.normalize("NFKC", name or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) not in _DROP_CATEGORIES)
    s = _FORBIDDEN.sub(" ", s)
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("._ -")
    if len(s) > max_len:
        s = s[:max_len].rstrip("._ -")
    if not s:
        return fallback
    if s.upper() in _RESERVED:
        s = f"_{s}"
    return s


def fmt_ts(seconds: float) -> str:
    """Secondi -> ``MM:SS`` oppure ``H:MM:SS``.

    >>> fmt_ts(792), fmt_ts(3723)
    ('13:12', '1:02:03')
    """
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_ts_file(seconds: float) -> str:
    """Secondi -> forma adatta ai nomi di file: ``13m18s`` / ``1h02m03s``."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"


def fmt_duration(seconds: float | None) -> str:
    """Durata leggibile: ``42 min``, ``1 h 05 min``."""
    if not seconds:
        return "durata sconosciuta"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{max(1, minutes)} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min"


def strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


_THOUSANDS = re.compile(r"(?<=\d)[.,'](?=\d{3}(?!\d))")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")
_NON_ALNUM = re.compile(r"[^0-9a-z.]+")


def normalize_for_match(text: str) -> str:
    """Normalizza per confronti tolleranti (verifica della provenienza dei numeri).

    Minuscole, niente accenti, separatori delle migliaia rimossi, virgola decimale -> punto.

    >>> normalize_for_match("Supporto dei 60.000, poi 1,5%")
    'supporto dei 60000 poi 1.5'
    """
    s = strip_accents(text.lower())
    prev = None
    while prev != s:  # applica più volte: "1.234.567" -> "1234567"
        prev = s
        s = _THOUSANDS.sub("", s)
    s = _DECIMAL_COMMA.sub(".", s)
    s = _NON_ALNUM.sub(" ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)  # punti che non sono decimali
    return re.sub(r"\s+", " ", s).strip()


def contains_normalized(haystack: str, needle: str) -> bool:
    n = normalize_for_match(needle)
    return bool(n) and f" {n} " in f" {normalize_for_match(haystack)} "


def format_number_it(value: float) -> str:
    """Formato numerico italiano, con precisione adatta alla grandezza.

    >>> format_number_it(60000), format_number_it(1.085), format_number_it(5821.25)
    ('60.000', '1,085', '5.821,25')
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "?"
    a = abs(value)
    if a >= 1000:
        decimals = 2
    elif a >= 1:
        decimals = 4
    else:
        decimals = 6
    text = f"{value:,.{decimals}f}"  # stile inglese: 5,821.25
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - len(suffix))].rstrip() + suffix
