"""Costruttori di dati finti condivisi dai test (nessuna rete)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ytkb.config import Settings
from ytkb.db import Database
from ytkb.llm.fake import FakeProvider
from ytkb.models import Transcript, VideoMeta
from ytkb.pipeline.context import PipelineContext
from ytkb.youtube.metadata import meta_from_info
from ytkb.youtube.transcripts import RawSnippet, RawTranscript, TranscriptService, TranscriptUnavailable

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def video_meta(name: str = "ytdlp_info_video.json", **overrides: Any) -> VideoMeta:
    info = load_json(name)
    info.update(overrides)
    return meta_from_info(info)


def btc_snippets() -> list[RawSnippet]:
    return [RawSnippet(**s) for s in load_json("transcript_btc_snippets.json")]


class StaticSource:
    """Fonte di trascrizione finta: restituisce sempre gli stessi frammenti, oppure solleva un errore."""

    def __init__(self, name: str, snippets: list[RawSnippet] | None = None, error: Exception | None = None,
                 language: str = "it"):
        self.name = name
        self._snippets = snippets
        self._error = error
        self._language = language
        self.calls = 0

    def fetch(self, meta: VideoMeta, languages) -> RawTranscript:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if not self._snippets:
            raise TranscriptUnavailable("nessun sottotitolo")
        return RawTranscript(self._language, True, self.name, list(self._snippets))


def seg_with(transcript: Transcript, phrase: str) -> int:
    for s in transcript.segments:
        if phrase in s.text:
            return s.id
    raise AssertionError(f"frase non trovata nella trascrizione: {phrase}")


def analysis_for(transcript: Transcript) -> dict[str, Any]:
    """Un output di analisi plausibile e valido per la trascrizione BTC della fixture."""
    s_btc = seg_with(transcript, "supporto dei 60.000")
    s_res = seg_with(transcript, "guardate questa resistenza")
    s_spx = seg_with(transcript, "range tra 5.750")
    s_theory = seg_with(transcript, "regola numero uno")
    s_slide = seg_with(transcript, "in questa slide")
    return {
        "video_type": "HYBRID",
        "source_language": "it",
        "tldr": ["BTC rialzista finché tiene 60.000 in chiusura giornaliera",
                 "S&P 500 neutrale in attesa del CPI di giovedì",
                 "Tre regole per disegnare un supporto"],
        "summary": "L'autore analizza Bitcoin e S&P 500 e spiega come disegnare i supporti.",
        "worth_watching": {"score": 3, "reason": "Setup BTC chiaro, resto generico",
                           "best_ranges": [{"start_segment": s_btc, "end_segment": s_res, "reason": "setup BTC"}]},
        "assets": [
            {"asset": "btc/usd", "asset_name": "Bitcoin", "timeframe": "1D", "bias": "BULLISH",
             "thesis": "Rimbalzo sul supporto dei 60.000",
             "levels": [
                 {"value": 60000, "kind": "SUPPORT", "note": "ha retto tre volte", "segment_id": s_btc,
                  "spoken_text": "supporto dei 60.000 dollari"},
                 {"value": 56500, "kind": "TARGET", "note": "se perde 60.000", "segment_id": s_btc,
                  "spoken_text": "il prossimo livello è 56.500"},
                 {"value": 64480, "kind": "RESISTANCE", "note": "inventato", "segment_id": s_res,
                  "spoken_text": "resistenza a 64.480"},
             ],
             "invalidation": "chiusura giornaliera sotto 60.000", "trade_idea": "",
             "segment_ids": [s_btc, s_res]},
            {"asset": "SPX", "asset_name": "S&P 500", "timeframe": "4H", "bias": "NEUTRAL",
             "thesis": "Laterale tra 5.750 e 5.900 fino al CPI",
             "levels": [{"value": 5750, "kind": "SUPPORT", "note": "", "segment_id": s_spx,
                         "spoken_text": "range tra 5.750 e 5.900"}],
             "invalidation": "", "trade_idea": "", "segment_ids": [s_spx]},
        ],
        "concepts": [{"title": "Come disegnare un supporto", "explanation": "Servono almeno due minimi.",
                      "steps": ["Almeno due minimi", "Più tocchi = più forza", "Conferma in chiusura"],
                      "examples": [], "segment_ids": [s_theory]}],
        "macro": [{"topic": "Inflazione USA", "view": "Mercato laterale fino al dato",
                   "upcoming_events": ["CPI giovedì"], "segment_ids": [s_spx]}],
        "visual_triggers": [
            {"start_segment": s_btc, "end_segment": s_btc, "trigger_type": "PRICE_CHART", "importance": 5,
             "asset": "BTCUSD", "needs_video_clip": False, "spoken_context": "prezzo sul supporto dei 60.000",
             "vision_question": "Quali livelli orizzontali sono disegnati?"},
            {"start_segment": s_slide, "end_segment": s_slide + 50, "trigger_type": "EDUCATIONAL_SLIDE",
             "importance": 4, "asset": "", "needs_video_clip": False, "spoken_context": "slide con le tre regole",
             "vision_question": "Trascrivi le regole della slide"},
        ],
        "chapters": [{"title": "Intro", "start_segment": 1}, {"title": "Bitcoin", "start_segment": s_btc},
                     {"title": "Teoria", "start_segment": s_theory}, {"title": "Doppione", "start_segment": s_btc}],
        "sponsor_or_conflicts": ["Sponsor: broker XYZ"],
        "caveats": [],
    }


def make_ctx(settings: Settings, db: Database, *, meta: VideoMeta | None = None,
             fetch_metadata: Callable[[str], VideoMeta] | None = None,
             sources: dict[str, Any] | None = None, llm: FakeProvider | None = None,
             clock: Callable | None = None, **kwargs: Any) -> PipelineContext:
    meta = meta or video_meta()
    if sources is None:
        sources = {"transcript_api": StaticSource("transcript_api", btc_snippets())}
    ctx = PipelineContext(
        settings=settings, db=db, llm=llm or FakeProvider(),
        fetch_metadata=fetch_metadata or (lambda vid: meta.model_copy(update={"video_id": vid})),
        transcripts=TranscriptService(settings, sources),
        **kwargs,
    )
    if clock is not None:
        ctx.clock = clock
    return ctx
