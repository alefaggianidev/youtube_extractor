"""Verifiche del codice sull'output del modello (D-003, D-005).

Il modello può sbagliare: qui correggiamo ID di segmento fuori intervallo, limitiamo i riferimenti visivi e
calcoliamo la provenienza dei numeri confrontandoli con la trascrizione.
"""

from __future__ import annotations

from typing import Literal

from ytkb.llm.schemas import AnalysisResult, PriceLevel, VisualTrigger
from ytkb.models import Transcript
from ytkb.utils.text import contains_normalized, normalize_for_match

Provenance = Literal["spoken", "unverified"]
MAX_TRIGGER_SEGMENTS = 3


def _clamp_triggers(triggers: list[VisualTrigger], t: Transcript, max_triggers: int) -> list[VisualTrigger]:
    fixed: list[VisualTrigger] = []
    for trig in triggers:
        start, end = t.clamp_id(trig.start_segment), t.clamp_id(trig.end_segment)
        if end < start:
            start, end = end, start
        end = min(end, start + MAX_TRIGGER_SEGMENTS - 1)
        fixed.append(trig.model_copy(update={"start_segment": start, "end_segment": end,
                                             "importance": max(1, min(5, trig.importance))}))
    # più importanti prima; a parità, prima nel video
    fixed.sort(key=lambda x: (-x.importance, x.start_segment))
    chosen: list[VisualTrigger] = []
    for trig in fixed:
        overlaps = any(abs(trig.start_segment - c.start_segment) <= 1 and trig.asset == c.asset for c in chosen)
        if not overlaps:
            chosen.append(trig)
        if len(chosen) >= max_triggers:
            break
    return sorted(chosen, key=lambda x: x.start_segment)


def postprocess_analysis(result: AnalysisResult, transcript: Transcript, max_triggers: int) -> AnalysisResult:
    t = transcript
    r = result.model_copy(deep=True)
    r.tldr = [p.strip() for p in r.tldr if p and p.strip()][:6]
    r.worth_watching.score = max(1, min(5, r.worth_watching.score))
    for rng in r.worth_watching.best_ranges:
        rng.start_segment, rng.end_segment = sorted((t.clamp_id(rng.start_segment), t.clamp_id(rng.end_segment)))
    for asset in r.assets:
        asset.asset = asset.asset.strip().upper().replace("/", "").replace(" ", "")
        asset.segment_ids = sorted({t.clamp_id(i) for i in asset.segment_ids})
        for level in asset.levels:
            level.segment_id = t.clamp_id(level.segment_id)
    for item in [*r.concepts, *r.macro]:
        item.segment_ids = sorted({t.clamp_id(i) for i in item.segment_ids})
    seen: set[int] = set()
    chapters = []
    for ch in sorted(r.chapters, key=lambda c: c.start_segment):
        ch.start_segment = t.clamp_id(ch.start_segment)
        if ch.start_segment not in seen and ch.title.strip():
            seen.add(ch.start_segment)
            chapters.append(ch)
    r.chapters = chapters
    for trig in r.visual_triggers:
        trig.asset = trig.asset.strip().upper().replace("/", "").replace(" ", "")
    r.visual_triggers = _clamp_triggers(r.visual_triggers, t, max_triggers)
    return r


def _number_forms(value: float) -> list[str]:
    forms = []
    if float(value).is_integer():
        forms.append(str(int(value)))
    else:
        forms.append(f"{value:.6f}".rstrip("0").rstrip("."))
    return [normalize_for_match(f) for f in forms]


def level_provenance(level: PriceLevel, transcript: Transcript) -> Provenance:
    """``spoken`` se il numero (o le parole riportate) si trovano davvero nella trascrizione attorno al segmento."""
    haystack = transcript.text_of(level.segment_id, context=1)
    if level.spoken_text and contains_normalized(haystack, level.spoken_text):
        return "spoken"
    norm = f" {normalize_for_match(haystack)} "
    if any(f" {form} " in norm for form in _number_forms(level.value)):
        return "spoken"
    return "unverified"
