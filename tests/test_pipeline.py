"""Pipeline completa con adapter finti: stati, checkpoint, costi."""

from datetime import timedelta

from tests.helpers import StaticSource, analysis_for, btc_snippets, make_ctx, video_meta
from ytkb.errors import PermanentError, TemporaryError
from ytkb.llm.fake import FakeProvider
from ytkb.models import Stage, Transcript, VideoStatus
from ytkb.pipeline.runner import Pipeline
from ytkb.youtube.transcripts import build_segments

VID = "dQw4w9WgXcQ"


def _analysis_responder(purpose, parts):
    t = Transcript(video_id=VID, language="it", source="x", segments=build_segments(btc_snippets(), 8, 14))
    return analysis_for(t)


def test_full_pipeline_manual_video(fine_settings, fine_db, fixed_now):
    llm = FakeProvider(responses={"analysis": _analysis_responder})
    ctx = make_ctx(fine_settings, fine_db, llm=llm, clock=lambda: fixed_now)
    row = Pipeline(ctx).process_now(VID)
    assert row.status == VideoStatus.DONE, row.last_error
    root = fine_settings.archive_dir / "Trading_Facile" / f"2026-10-26_BTC_e_S_P500_settimana_decisiva_Analisi_[{VID}]"
    assert root.exists(), list(fine_settings.archive_dir.rglob("*"))
    for name in ("metadata.json", "transcript.json", "transcript.txt", "analysis.json", "report.md", "report.html"):
        assert (root / name).exists(), name
    assert (root.parent / "channel_index.md").exists()
    assert "BTC e S&P500" in (root.parent / "channel_index.md").read_text(encoding="utf-8")
    assert "[13:12]" not in (root / "transcript.txt").read_text(encoding="utf-8")  # fixture breve
    purposes = [c.purpose for c in llm.calls]
    assert purposes.count("analysis") == 1 and "locate" in purposes  # stadi visivi eseguiti
    # l'utente vede 60.000 come "detto a voce"
    assert "🗣️ detto a voce" in (root / "report.md").read_text(encoding="utf-8")
    # costi registrati
    assert fine_db.llm_cost_summary(fixed_now - timedelta(days=1))[0]["purpose"] == "analysis"


def test_checkpoint_avoids_repeating_llm(fine_settings, fine_db, fixed_now):
    llm = FakeProvider(responses={"analysis": _analysis_responder})
    pipeline = Pipeline(make_ctx(fine_settings, fine_db, llm=llm, clock=lambda: fixed_now))
    pipeline.process_now(VID)
    calls_after_first = len(llm.calls)
    pipeline.process_now(VID)  # secondo giro: tutto già fatto, nessuna chiamata AI
    assert len(llm.calls) == calls_after_first
    pipeline.process_now(VID, force_from=Stage.ANALYSIS)
    assert [c.purpose for c in llm.calls].count("analysis") == 2


def test_automatic_short_is_skipped(fine_settings, fine_db, fixed_now):
    ctx = make_ctx(fine_settings, fine_db, meta=video_meta("ytdlp_info_short.json"), clock=lambda: fixed_now)
    fine_db.add_video("short123456", source="rss", now=fixed_now)
    row = Pipeline(ctx).run_next()
    assert row.status == VideoStatus.SKIPPED and row.skip_reason == "Short"


def test_upcoming_premiere_waits(fine_settings, fine_db, fixed_now):
    ctx = make_ctx(fine_settings, fine_db, meta=video_meta("ytdlp_info_upcoming.json"), clock=lambda: fixed_now)
    fine_db.add_video("upcoming123", source="rss", now=fixed_now)
    row = Pipeline(ctx).run_next()
    assert row.status == VideoStatus.WAITING
    assert row.next_attempt_at.startswith("2026-10-27T14:10")
    assert Pipeline(ctx).run_next() is None  # non ancora in scadenza


def test_fresh_video_waits_for_captions_then_completes(fine_settings, fine_db):
    meta = video_meta(duration=600)
    clock = {"now": meta.published_at + timedelta(minutes=10)}
    api = StaticSource("transcript_api", None)
    ctx = make_ctx(fine_settings, fine_db, meta=meta, sources={"transcript_api": api,
                   "gemini_url": StaticSource("gemini_url", btc_snippets())}, clock=lambda: clock["now"],
                   llm=FakeProvider(responses={"analysis": _analysis_responder}))
    fine_db.add_video(VID, source="rss", now=clock["now"])
    pipeline = Pipeline(ctx)
    assert pipeline.run_next().status == VideoStatus.WAITING
    clock["now"] += timedelta(minutes=15)
    api._snippets = btc_snippets()  # i sottotitoli sono arrivati
    row = pipeline.run_next()
    assert row.status == VideoStatus.DONE and row.attempts == 0


def test_temporary_errors_retry_with_backoff_then_fail(fine_settings, fine_db, fixed_now):
    clock = {"now": fixed_now}
    ctx = make_ctx(fine_settings, fine_db, meta=video_meta(duration=600),
                   sources={"transcript_api": StaticSource("transcript_api", error=TemporaryError("rete giù"))},
                   clock=lambda: clock["now"])
    fine_db.add_video(VID, source="rss", now=fixed_now)
    pipeline = Pipeline(ctx)
    row = pipeline.run_next()
    assert row.status == VideoStatus.QUEUED and row.attempts == 1
    assert row.next_attempt_at.startswith("2026-10-27T10:05")
    for _ in range(4):
        clock["now"] += timedelta(days=1)
        row = pipeline.run_next()
    assert row.status == VideoStatus.FAILED and row.attempts == 5
    assert "rete giù" in row.last_error


def test_permanent_error_fails_immediately(fine_settings, fine_db, fixed_now):
    def boom(_vid):
        raise PermanentError("Private video")

    ctx = make_ctx(fine_settings, fine_db, fetch_metadata=boom, clock=lambda: fixed_now)
    row = Pipeline(ctx).process_now(VID)
    assert row.status == VideoStatus.FAILED and "Private video" in row.last_error


def test_internal_bug_does_not_crash_worker(fine_settings, fine_db, fixed_now):
    ctx = make_ctx(fine_settings, fine_db, llm=FakeProvider(responses={"analysis": ValueError("bug!")}),
                   clock=lambda: fixed_now)
    row = Pipeline(ctx).process_now(VID)
    assert row.status == VideoStatus.QUEUED and "errore interno" in row.last_error


def test_daily_budget_pauses_automatic_videos(home, fixed_now):
    from ytkb.config import load_settings
    from ytkb.db import open_db

    s = load_settings(home, overrides={"llm": {"provider": "gemini", "daily_budget_usd": 0.01}})
    s.ensure_dirs()
    db = open_db(s.db_path)
    db.record_llm_call(video_id=None, purpose="analysis", model="m", service_tier="flex", input_tokens=1,
                       output_tokens=1, thought_tokens=0, video_tokens=0, cost_usd=0.02, now=fixed_now)
    ctx = make_ctx(s, db, meta=video_meta(duration=600), clock=lambda: fixed_now)
    db.add_video(VID, source="rss", now=fixed_now)
    row = Pipeline(ctx).run_next()
    assert row.status == VideoStatus.WAITING and "budget" in row.last_error
    # le richieste manuali non sono bloccate dal budget
    assert Pipeline(ctx).process_now(VID).status == VideoStatus.DONE


def test_demo_mode_produces_marked_report(fine_settings, fine_db, fixed_now):
    ctx = make_ctx(fine_settings, fine_db, clock=lambda: fixed_now)  # FakeProvider con risposte predefinite
    row = Pipeline(ctx).process_now(VID)
    assert row.status == VideoStatus.DONE, row.last_error
    from pathlib import Path

    md = (Path(row.archive_dir) / "report.md").read_text(encoding="utf-8")
    assert "Report dimostrativo" in md
