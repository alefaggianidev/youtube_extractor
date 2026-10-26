"""Stadi 4-6: localizza (Gemini guarda il video), cattura (pochi secondi via yt-dlp), leggi (vision sul frame).

Tutto qui è **opzionale**: qualunque errore viene annotato nel risultato e il report esce comunque (degrado elegante).
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ytkb.errors import YtkbError
from ytkb.llm.base import ImagePart, TextPart, VideoUrlPart
from ytkb.llm.prompting import render_prompt
from ytkb.llm.schemas import AnalysisResult, FrameReadResult, LocateResult
from ytkb.llm.transcribe import resolve_offset
from ytkb.models import Stage, Transcript, VideoMeta
from ytkb.pipeline.context import PipelineContext
from ytkb.pipeline.workspace import Workspace
from ytkb.report.labels import TRIGGER
from ytkb.utils.text import fmt_ts, fmt_ts_file, sanitize_filename
from ytkb.visual.framepick import pick_best
from ytkb.visual.models import VisualItem, VisualReport

log = logging.getLogger(__name__)
MIN_WINDOW_S = 6.0


def initial_items(meta: VideoMeta, transcript: Transcript, analysis: AnalysisResult, ctx: PipelineContext,
                  ) -> list[VisualItem]:
    v = ctx.settings.visual
    duration = meta.duration_s or transcript.duration_s
    items: list[VisualItem] = []
    for trig in analysis.visual_triggers[: v.max_triggers]:
        s, e = transcript.segment(trig.start_segment), transcript.segment(trig.end_segment)
        if s is None or e is None:
            continue
        start = max(0.0, s.start - v.locate_padding_s)
        end = e.end + v.locate_padding_s
        if duration:
            end = min(end, duration)
        if end - start < MIN_WINDOW_S:
            end = start + MIN_WINDOW_S
        default_t = s.start + min(5.0, max(0.0, (s.end - s.start) / 2))
        items.append(VisualItem(index=len(items), trigger=trig, window_start_s=round(start, 1),
                                window_end_s=round(end, 1), capture_s=round(default_t, 1)))
    return items


def _parallel(fn: Callable[[VisualItem], Any], items: Sequence[VisualItem], workers: int) -> list[Any]:
    """Esegue ``fn`` su ogni elemento; restituisce risultati o eccezioni, nello stesso ordine."""

    def safe(item: VisualItem) -> Any:
        try:
            return fn(item)
        except Exception as exc:  # noqa: BLE001 - gli errori diventano note sul singolo elemento
            return exc

    if workers <= 1 or len(items) <= 1:
        return [safe(i) for i in items]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ytkb-visual") as pool:
        return list(pool.map(safe, items))


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:240]}"


# ------------------------------------------------------------------------------------------
def _locate(ctx: PipelineContext, meta: VideoMeta, items: list[VisualItem], report: VisualReport) -> None:
    s = ctx.settings
    system = render_prompt("locate_system")

    def call(item: VisualItem):
        t = item.trigger
        text = render_prompt("locate_user", start=round(item.window_start_s), end=round(item.window_end_s),
                             start_label=fmt_ts(item.window_start_s), end_label=fmt_ts(item.window_end_s),
                             trigger_type=TRIGGER.get(t.trigger_type, t.trigger_type), asset=t.asset,
                             spoken_context=t.spoken_context, vision_question=t.vision_question)
        parts = [VideoUrlPart(meta.url, start_s=item.window_start_s, end_s=item.window_end_s,
                              fps=s.visual.locate_fps, resolution="high"), TextPart(text)]
        return ctx.llm.generate(purpose="locate", model=s.llm.models.visual, system=system, parts=parts,
                                schema=LocateResult, max_output_tokens=4000)

    results = _parallel(call, items, s.visual.parallel_requests)
    failures = 0
    for item, res in zip(items, results, strict=True):
        if isinstance(res, BaseException):
            failures += 1
            item.locate_error = _short(res)
            ctx.record_usage("locate", getattr(res, "usage", None))
            continue
        ctx.record_usage("locate", res.usage)
        item.locate = res.data
        t = resolve_offset(res.data.best_offset_s, item.window_start_s, item.window_end_s)
        item.capture_s = round(min(max(t, item.window_start_s), item.window_end_s), 1)
    if failures:
        report.notes.append(f"Localizza non riuscito per {failures} momenti su {len(items)}: "
                            "uso il momento indicato dalla trascrizione.")


def frame_name(item: VisualItem, taken: set[str]) -> str:
    t = item.trigger
    base = f"{fmt_ts_file(item.capture_s)}_{t.trigger_type.lower()}_{sanitize_filename(t.asset or 'schermo', 20)}"
    name, n = f"{base}.jpg", 2
    while name in taken:
        name, n = f"{base}_{n}.jpg", n + 1
    taken.add(name)
    return name


def _capture(ctx: PipelineContext, meta: VideoMeta, ws: Workspace, items: list[VisualItem],
             report: VisualReport) -> None:
    try:
        result = ctx.capturer.capture_frames(meta.video_id, [i.capture_s for i in items])
    except Exception as exc:  # noqa: BLE001 - stadio opzionale: mai far fallire il video
        if not isinstance(exc, YtkbError):
            log.exception("Errore imprevisto nella cattura dei frame")
        msg = _short(exc)
        for item in items:
            item.capture_error = "download non riuscito"
        report.notes.append(f"Screenshot non scaricati ({msg}). Nel report trovi comunque la descrizione e il link "
                            "al secondo esatto.")
        log.warning("Cattura dei frame non riuscita per %s: %s", meta.video_id, msg)
        return
    taken: set[str] = set()
    try:
        ws.frames_dir.mkdir(parents=True, exist_ok=True)
        for idx, item in enumerate(items):
            candidates = result.frames.get(idx, [])
            best = pick_best(candidates)
            if best is None:
                item.capture_error = "nessun fotogramma utilizzabile" if candidates else "sezione non scaricata"
                continue
            name = frame_name(item, taken)
            shutil.copyfile(best, ws.frames_dir / name)
            item.frame_file = f"frames/{name}"
    finally:
        result.cleanup()


def _read(ctx: PipelineContext, ws: Workspace, items: list[VisualItem]) -> None:
    s = ctx.settings
    system = render_prompt("read_system")

    def call(item: VisualItem):
        t = item.trigger
        data = (ws.root / item.frame_file).read_bytes()
        text = render_prompt("read_user", time_label=fmt_ts(item.capture_s), asset=t.asset,
                             spoken_context=t.spoken_context,
                             on_screen=item.locate.on_screen if item.locate else "",
                             vision_question=t.vision_question)
        return ctx.llm.generate(purpose="read", model=s.llm.models.visual, system=system,
                                parts=[ImagePart(data, "image/jpeg", "high"), TextPart(text)],
                                schema=FrameReadResult, max_output_tokens=4000)

    for item, res in zip(items, _parallel(call, items, s.visual.parallel_requests), strict=True):
        if isinstance(res, BaseException):
            item.read_error = _short(res)
            ctx.record_usage("read", getattr(res, "usage", None))
        else:
            ctx.record_usage("read", res.usage)
            item.read = res.data


def _clips(ctx: PipelineContext, meta: VideoMeta, ws: Workspace, items: list[VisualItem],
           report: VisualReport) -> None:
    v = ctx.settings.visual
    ranges, paths = [], []
    for item in items:
        a = item.window_start_s
        b = min(item.window_end_s, a + v.clip_max_s)
        ranges.append((a, b))
        paths.append(ws.clips_dir / f"{fmt_ts_file(a)}-{fmt_ts_file(b)}_{sanitize_filename(item.trigger.asset or 'clip', 20)}.mp4")
    try:
        created = set(ctx.capturer.capture_clips(meta.video_id, ranges, paths))
    except Exception as exc:  # noqa: BLE001
        if not isinstance(exc, YtkbError):
            log.exception("Errore imprevisto nella creazione delle clip")
        report.notes.append(f"Clip video non create ({_short(exc)}).")
        return
    for item, path in zip(items, paths, strict=True):
        if path in created:
            item.clip_file = f"clips/{path.name}"


def run_visual_stages(ctx: PipelineContext, meta: VideoMeta, ws: Workspace, transcript: Transcript,
                      analysis: AnalysisResult) -> VisualReport:
    v = ctx.settings.visual
    report = VisualReport(items=initial_items(meta, transcript, analysis, ctx))
    if not report.items:
        return report
    vid = meta.video_id

    if v.locate:
        if meta.availability not in ("public", "unknown"):
            report.notes.append("Localizza saltato: Gemini può guardare solo video pubblici.")
        else:
            ctx.db.update_video(vid, now=ctx.clock(), stage=Stage.LOCATE.value)
            _locate(ctx, meta, report.items, report)

    active = [i for i in report.items if not i.dropped]
    if v.capture and active:
        if ctx.capturer is None:
            report.notes.append("Cattura dei frame non disponibile in questa installazione.")
        else:
            ctx.db.update_video(vid, now=ctx.clock(), stage=Stage.CAPTURE.value)
            _capture(ctx, meta, ws, active, report)

    with_frames = [i for i in active if i.frame_file]
    if v.read_frame and with_frames:
        ctx.db.update_video(vid, now=ctx.clock(), stage=Stage.READ.value)
        _read(ctx, ws, with_frames)

    clip_items = [i for i in active if i.trigger.needs_video_clip]
    if v.clips and clip_items and ctx.capturer is not None:
        _clips(ctx, meta, ws, clip_items, report)

    dropped = len(report.items) - len(active)
    if dropped:
        report.notes.append(f"{dropped} momenti scartati: a schermo non c'era nulla di utile (es. solo webcam).")
    return report
