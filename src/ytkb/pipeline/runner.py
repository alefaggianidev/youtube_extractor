"""Orchestrazione degli 8 stadi e macchina a stati del video (D-008).

Ogni stadio salva il proprio artefatto; se l'artefatto esiste già (checkpoint) lo stadio viene saltato.
Il *tipo* di errore decide il nuovo stato del video:

=================  ==========================================================
SkipError          ``skipped``  (Short, filtri, non accessibile)
NotReadyError      ``waiting``  con ``next_attempt_at`` (premiere, live, sottotitoli, budget)
PermanentError     ``failed``
TemporaryError     ``queued`` con backoff, poi ``failed`` dopo ``worker.max_attempts``
=================  ==========================================================
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ytkb.db import VideoRow
from ytkb.errors import BudgetExceededError, NotReadyError, PermanentError, SkipError, TemporaryError
from ytkb.llm.base import TextPart
from ytkb.llm.prompting import render_prompt
from ytkb.llm.schemas import AnalysisResult
from ytkb.models import LiveStatus, Stage, Transcript, VideoMeta, VideoStatus
from ytkb.pipeline import workspace as W
from ytkb.pipeline.context import PipelineContext
from ytkb.pipeline.postprocess import postprocess_analysis
from ytkb.pipeline.readiness import check_readiness
from ytkb.pipeline.workspace import Workspace
from ytkb.report.channel_index import update_channel_index
from ytkb.report.render import write_reports
from ytkb.report.viewmodel import build_report_vm
from ytkb.utils.text import fmt_duration, fmt_ts, truncate
from ytkb.utils.timeutil import plus_minutes, to_iso
from ytkb.visual.models import VisualReport

log = logging.getLogger(__name__)

MANUAL_SOURCES = {"manual", "telegram"}
FINAL_LIVE_STATUSES = {LiveStatus.NOT_LIVE, LiveStatus.WAS_LIVE}


class Pipeline:
    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx

    # ------------------------------------------------------------------------------
    # API pubblica
    # ------------------------------------------------------------------------------
    def run_next(self) -> VideoRow | None:
        """Lavora il prossimo video in scadenza. Restituisce la riga aggiornata o ``None`` se non c'è nulla."""
        row = self.ctx.db.claim_next_due(now=self.ctx.clock())
        if row is None:
            return None
        self.process(row)
        return self.ctx.db.get_video(row.video_id)

    def run_pending(self, max_items: int | None = None) -> int:
        done = 0
        while max_items is None or done < max_items:
            if self.run_next() is None:
                break
            done += 1
        return done

    def process_now(self, video_id: str, force_from: Stage | None = None, source: str = "manual",
                    requested_by: str | None = None) -> VideoRow:
        """Lavora subito un video specifico, come richiesta manuale (ignora orario di riprova, filtri e budget)."""
        db, now = self.ctx.db, self.ctx.clock()
        if db.get_video(video_id) is None:
            db.add_video(video_id, source=source, priority=10, requested_by=requested_by, now=now)
        db.update_video(video_id, now=now, status=VideoStatus.PROCESSING, started_at=to_iso(now))
        row = db.get_video(video_id)
        assert row is not None
        self.process(row, force_from=force_from, manual=True)
        updated = db.get_video(video_id)
        assert updated is not None
        return updated

    # ------------------------------------------------------------------------------
    def process(self, row: VideoRow, force_from: Stage | None = None, manual: bool | None = None) -> VideoStatus:
        """Esegue gli stadi. ``manual`` (default: dedotto dalla fonte) disattiva filtri, attese e budget."""
        ctx, db = self.ctx, self.ctx.db
        ctx.current_video_id = row.video_id
        manual = row.source in MANUAL_SOURCES if manual is None else manual
        stage = Stage.METADATA
        title = row.title or row.video_id
        try:
            self._stage(row, stage)
            meta = self._metadata(row, manual=manual, force=force_from == Stage.METADATA)
            title = meta.title
            ws = Workspace.for_video(ctx.settings.archive_dir, meta, ctx.settings.report.timezone, row.archive_dir)
            if force_from is not None:
                ws.invalidate_from(force_from)
            ws.save(W.METADATA, meta)
            db.update_video(row.video_id, now=ctx.clock(), title=meta.title, channel_id=meta.channel_id,
                            channel_title=meta.channel_title, archive_dir=str(ws.root),
                            published_at=to_iso(meta.published_at))

            if not ws.has(W.ANALYSIS):
                self._check_budget(manual)

            stage = Stage.TRANSCRIPT
            self._stage(row, stage)
            transcript = self._transcript(row, meta, ws, manual)

            stage = Stage.ANALYSIS
            self._stage(row, stage)
            analysis = self._analysis(meta, ws, transcript)

            stage = Stage.LOCATE
            self._stage(row, stage)
            visual = self._visual(meta, ws, transcript, analysis)

            stage = Stage.RENDER
            self._stage(row, stage)
            vm = build_report_vm(meta, transcript, analysis, visual, ctx.settings, ws.root)
            _, html_path = write_reports(vm, ws.root)

            stage = Stage.PUBLISH
            self._stage(row, stage)
            self._publish(row, meta, ws, vm, html_path)

            db.update_video(row.video_id, now=ctx.clock(), status=VideoStatus.DONE, stage=Stage.PUBLISH.value,
                            finished_at=to_iso(ctx.clock()), last_error=None, next_attempt_at=None)
            db.add_event(row.video_id, "INFO", f"Report pronto: {ws.path(W.REPORT_MD)}", stage.value, now=ctx.clock())
            log.info("✅ %s — report in %s", title, ws.root)
            return VideoStatus.DONE

        except SkipError as exc:
            self._finish(row, VideoStatus.SKIPPED, stage, skip_reason=exc.reason)
            log.info("⏭️  %s saltato: %s", title, exc.reason)
            return VideoStatus.SKIPPED
        except NotReadyError as exc:
            minutes = exc.retry_after_minutes or 30
            nxt = plus_minutes(ctx.clock(), minutes)
            db.update_video(row.video_id, now=ctx.clock(), status=VideoStatus.WAITING, stage=stage.value,
                            next_attempt_at=to_iso(nxt), last_error=str(exc))
            db.add_event(row.video_id, "INFO", f"In attesa: {exc} (riprovo alle {nxt:%H:%M} UTC)", stage.value,
                         now=ctx.clock())
            log.info("⏳ %s in attesa (%s): riprovo tra %.0f minuti", title, exc, minutes)
            return VideoStatus.WAITING
        except PermanentError as exc:
            ctx.record_usage(stage.value, getattr(exc, "usage", None))
            self._finish(row, VideoStatus.FAILED, stage, error=str(exc))
            log.error("❌ %s fallito (errore permanente): %s", title, exc)
            self._notify_failure(row, title, str(exc))
            return VideoStatus.FAILED
        except TemporaryError as exc:
            ctx.record_usage(stage.value, getattr(exc, "usage", None))
            return self._retry_or_fail(row, stage, title, str(exc))
        except Exception as exc:  # noqa: BLE001 - un bug non deve fermare il worker
            log.exception("Errore interno durante %s di %s", stage.value, row.video_id)
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            return self._retry_or_fail(row, stage, title, f"errore interno: {detail}")
        finally:
            ctx.current_video_id = None

    # ------------------------------------------------------------------------------
    # Stadi
    # ------------------------------------------------------------------------------
    def _metadata(self, row: VideoRow, *, manual: bool, force: bool) -> VideoMeta:
        ctx = self.ctx
        cached = None
        if row.archive_dir and not force:
            cached = Workspace(row.archive_dir).load(W.METADATA, VideoMeta)
        if cached is not None and cached.live_status in FINAL_LIVE_STATUSES:
            meta = cached
        else:
            meta = ctx.fetch_metadata(row.video_id)
        filters = ctx.settings.filters.merged(ctx.channel_filters(meta.channel_id))
        check_readiness(meta, filters, manual=manual, now=ctx.clock())
        return meta

    def _transcript(self, row: VideoRow, meta: VideoMeta, ws: Workspace, manual: bool) -> Transcript:
        cached = ws.load(W.TRANSCRIPT, Transcript)
        if cached is not None:
            return cached
        transcript = self.ctx.transcripts.get(meta, now=self.ctx.clock(), allow_wait=not manual)
        ws.save(W.TRANSCRIPT, transcript)
        ws.write_text(W.TRANSCRIPT_TXT, f"{meta.title}\n{meta.url}\n\n{transcript.to_readable()}\n")
        return transcript

    def _analysis(self, meta: VideoMeta, ws: Workspace, transcript: Transcript) -> AnalysisResult:
        cached = ws.load(W.ANALYSIS, AnalysisResult)
        if cached is not None:
            return cached
        s = self.ctx.settings
        chapters = [f"{fmt_ts(c.start_s)} {c.title}" for c in meta.chapters]
        common = {"first_id": transcript.first_id, "last_id": transcript.last_id,
                  "max_triggers": s.visual.max_triggers}
        system = render_prompt("analysis_system", **common)
        user = render_prompt(
            "analysis_user", title=meta.title, channel=meta.channel_title,
            published=meta.published_at.date().isoformat() if meta.published_at else "sconosciuta",
            duration=fmt_duration(meta.duration_s), language=transcript.language,
            is_generated=transcript.is_generated, source=transcript.source, chapters=chapters,
            description=truncate(meta.description, 1500), n_segments=len(transcript.segments),
            transcript=transcript.to_prompt(), **common,
        )
        resp = self.ctx.llm.generate(purpose="analysis", model=s.llm.models.analysis, system=system,
                                     parts=[TextPart(user)], schema=AnalysisResult)
        self.ctx.record_usage("analysis", resp.usage)
        analysis = postprocess_analysis(resp.data, transcript, s.visual.max_triggers)
        ws.save(W.ANALYSIS, analysis)
        return analysis

    def _visual(self, meta: VideoMeta, ws: Workspace, transcript: Transcript,
                analysis: AnalysisResult) -> VisualReport | None:
        """Stadi 4-6 (localizza, cattura, leggi): opzionali, non fanno mai fallire il video."""
        if not self.ctx.settings.visual.enabled or not analysis.visual_triggers:
            return None
        cached = ws.load(W.VISUAL, VisualReport)
        if cached is not None:
            return cached
        try:
            from ytkb.visual.stage import run_visual_stages
        except ImportError:  # pragma: no cover - fase 2 non ancora disponibile
            return None
        try:
            report = run_visual_stages(self.ctx, meta, ws, transcript, analysis)
        except Exception as exc:  # noqa: BLE001 - degrado elegante: il report esce senza immagini
            log.exception("Stadi visivi non riusciti per %s", meta.video_id)
            return VisualReport(notes=[f"Riferimenti visivi non disponibili per un errore interno ({exc}). "
                                       f"Riprova con: ytkb process {meta.video_id} --from locate"])
        ws.save(W.VISUAL, report)
        return report

    def _publish(self, row: VideoRow, meta: VideoMeta, ws: Workspace, vm, html_path) -> None:
        try:
            update_channel_index(ws.channel_dir, self.ctx.settings.report.timezone)
        except OSError as exc:
            log.warning("Indice del canale non aggiornato: %s", exc)
        if self.ctx.notifier is not None:
            from ytkb.notify.format import summary_html

            try:
                self.ctx.notifier.video_done(video_id=meta.video_id, title=meta.title, channel=meta.channel_title,
                                             summary_html=summary_html(vm), report_html=html_path,
                                             requested_by=row.requested_by)
            except Exception as exc:  # noqa: BLE001 - la notifica è opzionale (degrado elegante)
                log.warning("Notifica non inviata per %s: %s", meta.video_id, exc)
                self.ctx.db.add_event(row.video_id, "WARNING", f"Notifica non inviata: {exc}", "publish",
                                      now=self.ctx.clock())

    # ------------------------------------------------------------------------------
    # Supporto
    # ------------------------------------------------------------------------------
    def _stage(self, row: VideoRow, stage: Stage) -> None:
        self.ctx.db.update_video(row.video_id, now=self.ctx.clock(), stage=stage.value)

    def _check_budget(self, manual: bool) -> None:
        s = self.ctx.settings
        if manual or s.llm.provider == "fake" or s.llm.daily_budget_usd <= 0:
            return
        tz = ZoneInfo(s.report.timezone)
        now = self.ctx.clock()
        local_now = now.astimezone(tz)
        midnight = datetime.combine(local_now.date(), time(0, 0), tzinfo=tz)
        spent = self.ctx.db.llm_cost_since(midnight)
        if spent >= s.llm.daily_budget_usd:
            minutes = (midnight + timedelta(days=1, minutes=5) - local_now).total_seconds() / 60
            raise BudgetExceededError(
                f"budget giornaliero raggiunto ({spent:.2f}$ su {s.llm.daily_budget_usd:.2f}$): riprendo domani",
                retry_after_minutes=minutes)

    def _finish(self, row: VideoRow, status: VideoStatus, stage: Stage, *, error: str | None = None,
                skip_reason: str | None = None) -> None:
        now = self.ctx.clock()
        self.ctx.db.update_video(row.video_id, now=now, status=status, stage=stage.value, last_error=error,
                                 skip_reason=skip_reason, finished_at=to_iso(now), next_attempt_at=None)
        self.ctx.db.add_event(row.video_id, "WARNING" if status == VideoStatus.SKIPPED else "ERROR",
                              f"{status.value}: {skip_reason or error}", stage.value, now=now)

    def _retry_or_fail(self, row: VideoRow, stage: Stage, title: str, message: str) -> VideoStatus:
        ctx = self.ctx
        current = ctx.db.get_video(row.video_id)
        attempts = (current.attempts if current else row.attempts) + 1
        w = ctx.settings.worker
        if attempts >= w.max_attempts:
            ctx.db.update_video(row.video_id, now=ctx.clock(), attempts=attempts)
            self._finish(row, VideoStatus.FAILED, stage, error=f"{message} (dopo {attempts} tentativi)")
            log.error("❌ %s fallito dopo %d tentativi: %s", title, attempts, message)
            self._notify_failure(row, title, message)
            return VideoStatus.FAILED
        backoff = w.retry_backoff_minutes
        minutes = backoff[min(attempts - 1, len(backoff) - 1)] if backoff else 15
        nxt = plus_minutes(ctx.clock(), minutes)
        ctx.db.update_video(row.video_id, now=ctx.clock(), status=VideoStatus.QUEUED, stage=stage.value,
                            attempts=attempts, next_attempt_at=to_iso(nxt), last_error=message)
        ctx.db.add_event(row.video_id, "WARNING", f"Errore temporaneo (tentativo {attempts}): {message}",
                         stage.value, now=ctx.clock())
        log.warning("⚠️  %s: errore temporaneo durante %s (tentativo %d, riprovo tra %.0f min): %s",
                    title, stage.value, attempts, minutes, message)
        return VideoStatus.QUEUED

    def _notify_failure(self, row: VideoRow, title: str, error: str) -> None:
        n = self.ctx.notifier
        if n is None or not self.ctx.settings.telegram.notify_on_failure:
            return
        try:
            n.video_failed(video_id=row.video_id, title=title, error=error, requested_by=row.requested_by)
        except Exception as exc:  # noqa: BLE001
            log.warning("Notifica di errore non inviata: %s", exc)
