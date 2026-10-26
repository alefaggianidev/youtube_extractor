"""Provider finto: per i test e per provare la pipeline senza chiave API (``llm.provider: fake``).

Le risposte predefinite sono costruite in modo deterministico a partire dalla trascrizione presente nel prompt,
così il report "finto" è comunque coerente con il video.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ytkb.llm.base import LLMResponse, LLMUsage, Part, T, TextPart, VideoUrlPart
from ytkb.llm.schemas import FrameReadResult, GeminiTranscript, LocateResult

_SEG = re.compile(r"^\[S(\d+) (\d+(?::\d+){1,2})\] (.*)$", re.MULTILINE)
_VISUAL_WORDS = ("grafico", "guardate", "vedete", "slide", "chart", "look at", "qui ")

Responder = Callable[[str, Sequence[Part]], Any]


@dataclass
class FakeCall:
    purpose: str
    model: str
    system: str
    parts: list[Part]
    schema: type[BaseModel]


@dataclass
class FakeProvider:
    """``responses`` per ``purpose``: dict/BaseModel (risposta), Exception (sollevata), callable(purpose, parts)."""

    responses: dict[str, Any] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)
    name: str = "fake"

    def generate(self, *, purpose: str, model: str, system: str, parts: Sequence[Part], schema: type[T],
                 max_output_tokens: int | None = None) -> LLMResponse[T]:
        self.calls.append(FakeCall(purpose, model, system, list(parts), schema))
        spec = self.responses.get(purpose)
        if callable(spec) and not isinstance(spec, type):
            spec = spec(purpose, parts)
        if isinstance(spec, BaseException):
            raise spec
        if spec is None:
            spec = default_response(purpose, parts)
        data = spec if isinstance(spec, schema) else schema.model_validate(spec)
        text = "".join(p.text for p in parts if isinstance(p, TextPart))
        usage = LLMUsage(model=model, service_tier="fake", input_tokens=len(text) // 4 + 50,
                         output_tokens=len(data.model_dump_json()) // 4, cost_usd=0.0)
        return LLMResponse(data=data, usage=usage, raw_text=data.model_dump_json())


def _segments_from_prompt(parts: Sequence[Part]) -> list[tuple[int, str]]:
    text = "\n".join(p.text for p in parts if isinstance(p, TextPart))
    return [(int(m.group(1)), m.group(3)) for m in _SEG.finditer(text)]


def default_response(purpose: str, parts: Sequence[Part]) -> dict[str, Any]:
    if purpose == "analysis":
        return _fake_analysis(parts)
    if purpose == "locate":
        return LocateResult(is_relevant=True, best_offset_s=3.0, content_type="PRICE_CHART",
                            on_screen="[DEMO] descrizione finta dello schermo", answer="[DEMO] risposta finta",
                            confidence="LOW").model_dump()
    if purpose == "read":
        return FrameReadResult(answer="[DEMO] lettura finta del grafico", legibility="LOW").model_dump()
    if purpose == "transcribe":
        video = next((p for p in parts if isinstance(p, VideoUrlPart)), None)
        start = video.start_s if video and video.start_s else 0
        return GeminiTranscript(language="it", lines=[
            {"start_s": 0.0, "text": f"[DEMO] trascrizione finta da {start:.0f} secondi"}]).model_dump()
    raise ValueError(f"FakeProvider: nessuna risposta per '{purpose}'")


def _fake_analysis(parts: Sequence[Part]) -> dict[str, Any]:
    segs = _segments_from_prompt(parts)
    first, last = (segs[0][0], segs[-1][0]) if segs else (1, 1)
    tldr = [f"[DEMO] {t[:140]}" for _, t in segs[:3]] or ["[DEMO] nessun contenuto"]
    triggers = []
    for sid, text in segs:
        if any(w in text.lower() for w in _VISUAL_WORDS):
            triggers.append({"start_segment": sid, "end_segment": sid, "trigger_type": "PRICE_CHART",
                             "importance": 3, "asset": "", "needs_video_clip": False,
                             "spoken_context": text[:160], "vision_question": "Cosa mostra lo schermo?"})
        if len(triggers) >= 3:
            break
    step = max(1, (last - first + 1) // 4)
    chapters = [{"title": f"[DEMO] Parte {i + 1}", "start_segment": first + i * step} for i in range(4)
                if first + i * step <= last]
    result = {
        "video_type": "OTHER",
        "source_language": "it",
        "tldr": tldr,
        "summary": "[DEMO] Questo è un riassunto finto generato senza modello AI (llm.provider: fake).",
        "worth_watching": {"score": 3, "reason": "[DEMO] punteggio finto",
                           "best_ranges": [{"start_segment": first, "end_segment": min(last, first + 2),
                                            "reason": "[DEMO] inizio del video"}]},
        "assets": [], "concepts": [], "macro": [],
        "visual_triggers": triggers,
        "chapters": chapters,
        "sponsor_or_conflicts": [],
        "caveats": ["Report dimostrativo: configura GEMINI_API_KEY e llm.provider: gemini per l'analisi vera."],
    }
    json.dumps(result)  # deve essere serializzabile
    return result
