"""Un unico "modello del report" da cui si generano sia il Markdown sia l'HTML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ytkb.config import Settings
from ytkb.llm.schemas import AnalysisResult
from ytkb.models import Transcript, VideoMeta
from ytkb.pipeline.postprocess import level_provenance
from ytkb.report import labels as L
from ytkb.utils.text import fmt_duration, fmt_ts, format_number_it
from ytkb.utils.timeutil import utcnow
from ytkb.visual.models import VisualItem, VisualReport
from ytkb.youtube.urls import timestamp_url


@dataclass
class LinkVM:
    label: str
    url: str


@dataclass
class LevelVM:
    value: str
    kind: str
    note: str
    badge: str
    provenance: str
    provenance_label: str
    link: LinkVM | None


@dataclass
class ReadingVM:
    label: str
    value: str


@dataclass
class VisualVM:
    number: int
    link: LinkVM
    type_label: str
    asset: str
    spoken_context: str
    question: str
    on_screen: str
    answer: str
    readings: list[ReadingVM]
    image_rel: str | None
    image_path: Path | None
    clip_rel: str | None
    confidence: str
    notes: list[str]


@dataclass
class AssetVM:
    asset: str
    name: str
    timeframe: str
    bias_emoji: str
    bias_label: str
    bias_key: str
    thesis: str
    levels: list[LevelVM]
    invalidation: str
    trade_idea: str
    links: list[LinkVM]
    visuals: list[VisualVM] = field(default_factory=list)


@dataclass
class ConceptVM:
    title: str
    explanation: str
    steps: list[str]
    examples: list[str]
    links: list[LinkVM]


@dataclass
class MacroVM:
    topic: str
    view: str
    events: list[str]
    links: list[LinkVM]


@dataclass
class RangeVM:
    label: str
    url: str
    reason: str


@dataclass
class ReportVM:
    video_id: str
    title: str
    channel: str
    video_url: str
    published: str
    duration: str
    video_type: str
    transcript_info: str
    tldr: list[str]
    summary: str
    worth_score: int
    worth_stars: str
    worth_reason: str
    worth_ranges: list[RangeVM]
    assets: list[AssetVM]
    concepts: list[ConceptVM]
    macro: list[MacroVM]
    other_visuals: list[VisualVM]
    chapters: list[LinkVM]
    sponsor: list[str]
    caveats: list[str]
    visual_notes: list[str]
    generated_at: str
    frontmatter: dict[str, Any]
    is_demo: bool = False


def _link(video_id: str, seconds: float) -> LinkVM:
    return LinkVM(fmt_ts(seconds), timestamp_url(video_id, seconds))


def _seg_links(video_id: str, transcript: Transcript, ids: list[int], limit: int = 4) -> list[LinkVM]:
    out = []
    for sid in sorted(set(ids))[:limit]:
        seg = transcript.segment(sid)
        if seg:
            out.append(_link(video_id, seg.start))
    return out


def _visual_vm(number: int, item: VisualItem, video_id: str, ws_root: Path | None) -> VisualVM:
    trig = item.trigger
    on_screen = item.locate.on_screen if item.locate else ""
    answer = ""
    readings: list[ReadingVM] = []
    confidence = ""
    notes: list[str] = []
    if item.read:
        answer = item.read.answer
        readings = [ReadingVM(r.label, r.value) for r in item.read.readings]
        confidence = L.CONFIDENCE.get(item.read.legibility, "")
        if item.read.notes:
            notes.append(item.read.notes)
    elif item.locate:
        answer = item.locate.answer
        readings = [ReadingVM(r.label, r.value) for r in item.locate.readings]
        confidence = L.CONFIDENCE.get(item.locate.confidence, "")
    if not item.frame_file:
        notes.append("Screenshot non disponibile" + (f" ({item.capture_error})" if item.capture_error else "")
                     + ": usa il link per vedere il momento esatto.")
    image_path = (ws_root / item.frame_file) if (ws_root and item.frame_file) else None
    return VisualVM(
        number=number,
        link=_link(video_id, item.capture_s),
        type_label=L.TRIGGER.get(trig.trigger_type, "Schermata"),
        asset=trig.asset,
        spoken_context=trig.spoken_context,
        question=trig.vision_question,
        on_screen=on_screen,
        answer=answer,
        readings=readings,
        image_rel=item.frame_file or None,
        image_path=image_path if image_path and image_path.exists() else None,
        clip_rel=item.clip_file or None,
        confidence=confidence,
        notes=notes,
    )


def build_report_vm(meta: VideoMeta, transcript: Transcript, analysis: AnalysisResult,
                    visual: VisualReport | None, settings: Settings, ws_root: Path | None = None) -> ReportVM:
    vid = meta.video_id
    tz = settings.report.timezone

    # --- visual: assegnati agli asset quando possibile -----------------------------
    visual_vms: list[tuple[str, VisualVM]] = []
    if visual:
        n = 0
        for item in visual.items:
            if item.dropped:
                continue
            n += 1
            visual_vms.append((item.trigger.asset, _visual_vm(n, item, vid, ws_root)))

    assets: list[AssetVM] = []
    used: set[int] = set()
    for a in analysis.assets:
        emoji, bias_label = L.BIAS.get(a.bias, ("⚪", a.bias))
        levels = []
        for lv in a.levels:
            prov = level_provenance(lv, transcript)
            badge, prov_label = L.PROVENANCE[prov]
            seg = transcript.segment(lv.segment_id)
            levels.append(LevelVM(format_number_it(lv.value), L.LEVEL_KIND.get(lv.kind, "Livello"), lv.note, badge,
                                  prov, prov_label, _link(vid, seg.start) if seg else None))
        asset_visuals = []
        for i, (asset_key, vm) in enumerate(visual_vms):
            if asset_key and asset_key == a.asset and i not in used:
                used.add(i)
                asset_visuals.append(vm)
        assets.append(AssetVM(a.asset, a.asset_name, a.timeframe, emoji, bias_label, a.bias, a.thesis, levels,
                              a.invalidation, a.trade_idea, _seg_links(vid, transcript, a.segment_ids),
                              asset_visuals))
    other_visuals = [vm for i, (_, vm) in enumerate(visual_vms) if i not in used]

    ranges = []
    for rng in analysis.worth_watching.best_ranges:
        s, e = transcript.segment(rng.start_segment), transcript.segment(rng.end_segment)
        if s and e:
            ranges.append(RangeVM(f"{fmt_ts(s.start)}–{fmt_ts(e.end)}", timestamp_url(vid, s.start), rng.reason))

    chapters = []
    for ch in analysis.chapters:
        seg = transcript.segment(ch.start_segment)
        if seg:
            chapters.append(LinkVM(f"{fmt_ts(seg.start)} — {ch.title}", timestamp_url(vid, seg.start)))

    kind = "automatica" if transcript.is_generated else "dell'autore"
    source_label = {"transcript_api": "sottotitoli YouTube", "ytdlp_subs": "sottotitoli YouTube",
                    "gemini_url": "trascritta da Gemini"}.get(transcript.source, transcript.source)
    is_demo = any("[DEMO]" in p for p in analysis.tldr)
    frontmatter: dict[str, Any] = {
        "title": meta.title,
        "channel": meta.channel_title,
        "video_id": vid,
        "url": meta.url,
        "published": meta.published_at.date().isoformat() if meta.published_at else None,
        "duration_min": round((meta.duration_s or 0) / 60),
        "type": analysis.video_type,
        "worth_watching": analysis.worth_watching.score,
        "assets": [a.asset for a in analysis.assets],
        "bias": {a.asset: a.bias.lower() for a in analysis.assets},
        "language": transcript.language,
        "tags": ["ytkb", analysis.video_type.lower()] + [a.asset.lower() for a in analysis.assets][:8],
    }
    return ReportVM(
        video_id=vid,
        title=meta.title,
        channel=meta.channel_title or "Canale sconosciuto",
        video_url=meta.url,
        published=L.date_it(meta.published_at or meta.upload_date, tz),
        duration=fmt_duration(meta.duration_s),
        video_type=L.VIDEO_TYPE.get(analysis.video_type, analysis.video_type),
        transcript_info=f"{kind}, {source_label}, lingua {transcript.language}",
        tldr=analysis.tldr,
        summary=analysis.summary,
        worth_score=analysis.worth_watching.score,
        worth_stars=L.stars(analysis.worth_watching.score),
        worth_reason=analysis.worth_watching.reason,
        worth_ranges=ranges,
        assets=assets,
        concepts=[ConceptVM(c.title, c.explanation, c.steps, c.examples, _seg_links(vid, transcript, c.segment_ids))
                  for c in analysis.concepts],
        macro=[MacroVM(m.topic, m.view, m.upcoming_events, _seg_links(vid, transcript, m.segment_ids))
               for m in analysis.macro],
        other_visuals=other_visuals,
        chapters=chapters,
        sponsor=analysis.sponsor_or_conflicts,
        caveats=analysis.caveats,
        visual_notes=visual.notes if visual else [],
        generated_at=L.date_it(utcnow(), tz, with_time=True),
        frontmatter=frontmatter,
        is_demo=is_demo,
    )
