"""Stadio 2: trascrizione con catena di fonti (D-006) e divisione in segmenti numerati (D-003).

Fonti, nell'ordine configurato in ``transcript.sources``:

1. ``transcript_api`` — youtube-transcript-api (veloce, solo testo);
2. ``ytdlp_subs``     — sottotitoli scaricati da yt-dlp in formato json3;
3. ``gemini_url``     — Gemini "ascolta" il video dal link YouTube (nessun download da parte nostra).

Se il video è appena uscito e non ci sono ancora sottotitoli, prima di usare la fonte a pagamento (Gemini)
si aspetta un po': spesso i sottotitoli automatici arrivano e costano zero.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ytkb.config import Settings
from ytkb.errors import BlockedError, NotReadyError, PermanentError, TemporaryError, YtkbError
from ytkb.models import Transcript, TranscriptSegment, VideoMeta
from ytkb.youtube.urls import watch_url
from ytkb.youtube.ytdlp import base_options, classify_error

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Strutture e errori
# --------------------------------------------------------------------------------------
@dataclass
class RawSnippet:
    start: float
    duration: float
    text: str


@dataclass
class RawTranscript:
    language: str
    is_generated: bool
    source: str
    snippets: list[RawSnippet] = field(default_factory=list)


class TranscriptUnavailable(YtkbError):
    """Questa fonte non ha (ancora) una trascrizione per il video."""


class TranscriptSource(Protocol):
    name: str

    def fetch(self, meta: VideoMeta, languages: Sequence[str]) -> RawTranscript: ...


def _base(lang: str | None) -> str:
    return (lang or "").split("-")[0].lower()


# --------------------------------------------------------------------------------------
# Scelta della lingua
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TrackInfo:
    language_code: str
    is_generated: bool


def pick_track(tracks: Sequence[TrackInfo], original_lang: str | None, preferred: Sequence[str]) -> int | None:
    """Sceglie la traccia migliore e ne restituisce l'indice.

    Ordine: manuale nella lingua originale > automatica nella lingua originale > manuale in una lingua preferita
    > automatica (di solito è la lingua parlata) > qualsiasi manuale.
    """
    if not tracks:
        return None
    orig = _base(original_lang)
    if not orig:  # la traccia automatica è (quasi sempre) nella lingua parlata
        gen = next((t for t in tracks if t.is_generated), None)
        orig = _base(gen.language_code) if gen else ""

    def find(pred: Callable[[TrackInfo], bool]) -> int | None:
        return next((i for i, t in enumerate(tracks) if pred(t)), None)

    candidates: list[Callable[[TrackInfo], bool]] = []
    if orig:
        candidates += [lambda t: not t.is_generated and _base(t.language_code) == orig,
                       lambda t: t.is_generated and _base(t.language_code) == orig]
    for lang in preferred:
        candidates.append(lambda t, lang=lang: not t.is_generated and _base(t.language_code) == _base(lang))
    candidates += [lambda t: t.is_generated, lambda t: True]
    for pred in candidates:
        idx = find(pred)
        if idx is not None:
            return idx
    return None


# --------------------------------------------------------------------------------------
# Fonte 1: youtube-transcript-api
# --------------------------------------------------------------------------------------
class TranscriptApiSource:
    name = "transcript_api"

    def __init__(self, settings: Settings, api_factory: Callable[[], Any] | None = None):
        self._settings = settings
        self._api_factory = api_factory or self._default_api

    def _default_api(self) -> Any:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.proxies import GenericProxyConfig

        proxy = self._settings.secrets.reveal(self._settings.secrets.ytkb_proxy)
        cfg = GenericProxyConfig(http_url=proxy, https_url=proxy) if proxy else None
        return YouTubeTranscriptApi(proxy_config=cfg)

    def fetch(self, meta: VideoMeta, languages: Sequence[str]) -> RawTranscript:
        import youtube_transcript_api as yta

        api = self._api_factory()
        try:
            tlist = list(api.list(meta.video_id))
            tracks = [TrackInfo(t.language_code, bool(t.is_generated)) for t in tlist]
            idx = pick_track(tracks, meta.language or meta.original_caption_lang, languages)
            if idx is None:
                raise TranscriptUnavailable("nessuna traccia di sottotitoli")
            fetched = tlist[idx].fetch()
        except TranscriptUnavailable:
            raise
        except (yta.RequestBlocked, yta.IpBlocked, yta.PoTokenRequired) as exc:
            raise BlockedError(f"youtube-transcript-api bloccata: {type(exc).__name__}") from exc
        except (yta.TranscriptsDisabled, yta.NoTranscriptFound) as exc:
            raise TranscriptUnavailable(type(exc).__name__) from exc
        except (yta.VideoUnavailable, yta.InvalidVideoId) as exc:
            raise PermanentError(f"video non disponibile: {type(exc).__name__}") from exc
        except (yta.AgeRestricted, yta.VideoUnplayable) as exc:
            raise TranscriptUnavailable(type(exc).__name__) from exc
        except yta.YouTubeTranscriptApiException as exc:
            raise TemporaryError(f"youtube-transcript-api: {type(exc).__name__}") from exc
        snippets = [RawSnippet(float(s.start), float(s.duration), s.text) for s in fetched.snippets]
        return RawTranscript(fetched.language_code, bool(fetched.is_generated), self.name, snippets)


# --------------------------------------------------------------------------------------
# Fonte 2: sottotitoli via yt-dlp (json3)
# --------------------------------------------------------------------------------------
def parse_json3(data: dict[str, Any]) -> list[RawSnippet]:
    """Interpreta il formato json3 dei sottotitoli YouTube."""
    out: list[RawSnippet] = []
    for ev in data.get("events") or []:
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        start = float(ev.get("tStartMs", 0)) / 1000
        dur = float(ev.get("dDurationMs", 0)) / 1000
        if out and out[-1].text == text:  # righe ripetute dei sottotitoli "a rullo"
            continue
        out.append(RawSnippet(start, dur, text))
    return out


def pick_ytdlp_lang(meta: VideoMeta, preferred: Sequence[str]) -> tuple[str, bool] | None:
    """Sceglie (codice lingua, è_automatica) tra i sottotitoli elencati nei metadati."""
    orig = _base(meta.language) or meta.original_caption_lang or ""
    manual = meta.subtitle_langs
    auto = meta.auto_caption_langs
    for lang in manual:
        if orig and _base(lang) == orig:
            return lang, False
    if orig and f"{orig}-orig" in auto:
        return f"{orig}-orig", True
    for lang in auto:
        if lang.endswith("-orig"):
            return lang, True
    if orig and orig in auto:
        return orig, True
    for pref in preferred:
        for lang in manual:
            if _base(lang) == _base(pref):
                return lang, False
    if manual:
        return manual[0], False
    return None


class YtdlpSubsSource:
    name = "ytdlp_subs"

    def __init__(self, settings: Settings, downloader: Callable[[str, dict[str, Any]], None] | None = None):
        self._settings = settings
        self._download = downloader or self._default_download

    @staticmethod
    def _default_download(url: str, opts: dict[str, Any]) -> None:
        import yt_dlp

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    def fetch(self, meta: VideoMeta, languages: Sequence[str]) -> RawTranscript:
        choice = pick_ytdlp_lang(meta, languages)
        if choice is None:
            raise TranscriptUnavailable("nessun sottotitolo elencato da yt-dlp")
        lang, is_auto = choice
        with tempfile.TemporaryDirectory(dir=self._settings.work_dir) as tmp:
            opts = base_options(self._settings) | {
                "skip_download": True,
                "ignore_no_formats_error": True,  # i sottotitoli servono anche se i formati video sono limitati
                "writesubtitles": not is_auto,
                "writeautomaticsub": is_auto,
                "subtitleslangs": [lang],
                "subtitlesformat": "json3",
                "outtmpl": {"default": str(Path(tmp) / "%(id)s.%(ext)s")},
            }
            try:
                self._download(watch_url(meta.video_id), opts)
            except Exception as exc:  # noqa: BLE001
                raise classify_error(exc) from exc
            files = sorted(Path(tmp).glob("*.json3"))
            if not files:
                raise TranscriptUnavailable(f"yt-dlp non ha scaricato i sottotitoli '{lang}'")
            data = json.loads(files[0].read_text(encoding="utf-8"))
        snippets = parse_json3(data)
        if not snippets:
            raise TranscriptUnavailable("sottotitoli vuoti")
        return RawTranscript(lang.removesuffix("-orig"), is_auto, self.name, snippets)


# --------------------------------------------------------------------------------------
# Segmentazione
# --------------------------------------------------------------------------------------
_NOISE = re.compile(r"\[(?:musica|music|applausi|applause|risate|laughter|__)\]|>>", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = _NOISE.sub(" ", text.replace("\n", " "))
    return re.sub(r"\s+", " ", text).strip()


def build_segments(snippets: Iterable[RawSnippet], target_s: float = 20, max_s: float = 40) -> list[TranscriptSegment]:
    """Unisce i frammenti (2–5 s) in segmenti numerati di ~``target_s`` secondi, spezzando a fine frase quando possibile."""
    items = sorted((s for s in snippets if clean_text(s.text)), key=lambda s: s.start)
    segments: list[TranscriptSegment] = []
    buf: list[str] = []
    seg_start: float | None = None
    seg_end = 0.0

    def flush() -> None:
        nonlocal buf, seg_start, seg_end
        if buf and seg_start is not None:
            segments.append(TranscriptSegment(id=len(segments) + 1, start=round(seg_start, 2),
                                              end=round(seg_end, 2), text=" ".join(buf)))
        buf, seg_start, seg_end = [], None, 0.0

    for sn in items:
        text = clean_text(sn.text)
        if seg_start is not None and (sn.start - seg_start) >= max_s:
            flush()
        if seg_start is None:
            seg_start = sn.start
        buf.append(text)
        seg_end = max(seg_end, sn.start + max(sn.duration, 0.0))
        length = seg_end - seg_start
        if length >= max_s or (length >= target_s and text.endswith((".", "?", "!"))) or length >= target_s * 1.5:
            flush()
    flush()
    for prev, nxt in zip(segments, segments[1:], strict=False):  # niente sovrapposizioni
        if prev.end > nxt.start:
            prev.end = nxt.start
    return segments


def to_transcript(video_id: str, raw: RawTranscript, settings: Settings) -> Transcript:
    segments = build_segments(raw.snippets, settings.transcript.segment_target_s, settings.transcript.segment_max_s)
    if not segments:
        raise TranscriptUnavailable("trascrizione vuota")
    return Transcript(video_id=video_id, language=_base(raw.language) or raw.language, source=raw.source,
                      is_generated=raw.is_generated, segments=segments)


# --------------------------------------------------------------------------------------
# Servizio: prova le fonti in ordine
# --------------------------------------------------------------------------------------
def captions_wait_minutes(schedule: Sequence[float], elapsed_min: float) -> float | None:
    """Quanto aspettare ancora i sottotitoli automatici, dato il tempo trascorso dalla pubblicazione.

    ``schedule`` sono le attese successive (es. 20, 40, 60, 120 → controlli a 20, 60, 120, 240 minuti).
    Restituisce ``None`` quando l'attesa è finita.
    """
    total = 0.0
    for step in schedule:
        total += step
        if elapsed_min < total:
            return max(1.0, total - elapsed_min)
    return None


class TranscriptService:
    PAID_SOURCES = {"gemini_url"}

    def __init__(self, settings: Settings, sources: dict[str, TranscriptSource]):
        self._settings = settings
        self._sources = sources

    def get(self, meta: VideoMeta, *, now: datetime, allow_wait: bool = True) -> Transcript:
        errors: list[str] = []
        blocked = False
        temporary = False
        cfg = self._settings.transcript
        for name in cfg.sources:
            source = self._sources.get(name)
            if source is None:
                continue
            if name in self.PAID_SOURCES:
                if allow_wait and meta.published_at:
                    elapsed = (now - meta.published_at).total_seconds() / 60
                    wait = captions_wait_minutes(cfg.wait_for_captions_minutes, elapsed)
                    if wait is not None and not blocked:
                        raise NotReadyError(
                            f"sottotitoli non ancora disponibili ({'; '.join(errors) or 'nessuna fonte'}): "
                            f"riprovo tra {wait:.0f} minuti", retry_after_minutes=wait)
                if not meta.is_public:
                    errors.append(f"{name}: il video non è pubblico")
                    continue
            try:
                raw = source.fetch(meta, cfg.languages)
                transcript = to_transcript(meta.video_id, raw, self._settings)
                log.info("Trascrizione da %s: %d segmenti, lingua %s", name, len(transcript.segments),
                         transcript.language)
                return transcript
            except TranscriptUnavailable as exc:
                errors.append(f"{name}: {exc}")
            except BlockedError as exc:
                blocked = True
                errors.append(f"{name}: BLOCCATO ({exc})")
            except NotReadyError:
                raise
            except TemporaryError as exc:
                temporary = True
                errors.append(f"{name}: {exc}")
        summary = "; ".join(errors) or "nessuna fonte configurata"
        if blocked:
            raise BlockedError(f"Trascrizione non ottenuta, YouTube blocca le richieste: {summary}")
        if temporary:
            raise TemporaryError(f"Trascrizione non ottenuta: {summary}")
        raise PermanentError(f"Nessuna trascrizione disponibile: {summary}")
