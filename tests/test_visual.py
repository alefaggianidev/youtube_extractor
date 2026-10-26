"""Stadi visivi: scelta del frame, cattura con yt-dlp (simulato) + ffmpeg (vero), orchestrazione."""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

from tests.helpers import analysis_for, btc_snippets, make_ctx, video_meta
from ytkb.errors import BlockedError, TemporaryError
from ytkb.llm.fake import FakeProvider
from ytkb.llm.schemas import AnalysisResult
from ytkb.models import Transcript
from ytkb.pipeline.postprocess import postprocess_analysis
from ytkb.pipeline.workspace import Workspace
from ytkb.visual.framepick import load_gray, pick_best, sharpness
from ytkb.visual.stage import run_visual_stages
from ytkb.youtube.media import (
    CaptureResult,
    FrameCapturer,
    Section,
    _match_files,
    capture_options,
    video_format,
)
from ytkb.youtube.transcripts import build_segments

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _chart(path: Path, blur: float = 0.0, uniform: bool = False) -> Path:
    img = Image.new("RGB", (800, 450), (20, 24, 34))
    if not uniform:
        d = ImageDraw.Draw(img)
        for i in range(40):
            d.rectangle([20 + i * 19, 200 - (i % 7) * 12, 30 + i * 19, 260 + (i % 5) * 9], fill=(38, 166, 154))
        d.line([(0, 300), (800, 300)], fill=(255, 235, 59), width=2)
        d.text((700, 285), "60.000", fill=(255, 235, 59))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    img.save(path, quality=90)
    return path


# --- scelta del frame -------------------------------------------------------------------------
def test_pick_best_prefers_sharp_and_skips_uniform(tmp_path):
    sharp = _chart(tmp_path / "a.jpg")
    blurry = _chart(tmp_path / "b.jpg", blur=4)
    flat = _chart(tmp_path / "c.jpg", uniform=True)
    assert sharpness(load_gray(sharp)) > sharpness(load_gray(blurry))
    assert pick_best([blurry, flat, sharp]) == sharp
    assert pick_best([flat]) is None
    assert pick_best([tmp_path / "manca.jpg"]) is None


# --- cattura ------------------------------------------------------------------------------------
def test_capture_options(settings, tmp_path):
    opts = capture_options(settings, [Section(10, 13), Section(40.5, 43.5)], tmp_path, with_audio=False, height=1080)
    assert opts["format"] == video_format(1080) and "height<=1080" in opts["format"]
    ranges = list(opts["download_ranges"]({"duration": 1000}, None))
    assert [(r["start_time"], r["end_time"]) for r in ranges] == [(10, 13), (40.5, 43.5)]
    assert opts["outtmpl"]["default"].endswith("sec_%(section_start)s.%(ext)s")


def test_match_files(tmp_path):
    for name in ("sec_10.0.mp4", "sec_40.5.mp4", "sec_40.5.mp4.part", "altro.txt"):
        (tmp_path / name).write_bytes(b"x")
    found = _match_files(tmp_path, [Section(10, 13), Section(40.5, 43.5), Section(99, 102)])
    assert {k: v.name for k, v in found.items()} == {0: "sec_10.0.mp4", 1: "sec_40.5.mp4"}


def _fake_ytdlp(url, opts):
    """Simula yt-dlp: per ogni sezione crea un piccolo video (vero, generato da ffmpeg)."""
    template = opts["outtmpl"]["default"]
    for r in opts["download_ranges"]({"duration": 1000}, None):
        out = template.replace("%(section_start)s", str(float(r["start_time"]))).replace("%(ext)s", "mp4")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=size=640x360:rate=10", "-t", "3", "-pix_fmt", "yuv420p", out], check=True)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg non installato")
def test_capture_frames_with_real_ffmpeg(settings):
    cap = FrameCapturer(settings, downloader=_fake_ytdlp)
    result = cap.capture_frames("dQw4w9WgXcQ", [22.0, 104.0], frames_per_moment=3)
    try:
        assert sorted(result.frames) == [0, 1]
        assert all(len(f) == 3 and all(p.exists() and p.stat().st_size > 0 for p in f) for f in result.frames.values())
        assert pick_best(result.frames[0]) is not None
    finally:
        result.cleanup()
    assert not result.tmp.exists()


def test_capture_errors_are_typed_and_cleaned(settings):
    def blocked(url, opts):
        raise RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot")

    cap = FrameCapturer(settings, downloader=blocked)
    with pytest.raises(BlockedError):
        cap.capture_frames("dQw4w9WgXcQ", [22.0])
    assert not any(p.name.startswith("cap_") for p in settings.work_dir.iterdir())  # niente cartelle orfane


# --- orchestrazione degli stadi 4-6 ---------------------------------------------------------------
class FakeCapturer:
    def __init__(self, tmp: Path, error: Exception | None = None):
        self.tmp, self.error, self.moments = tmp, error, []

    def capture_frames(self, video_id, moments, frames_per_moment=None):
        if self.error:
            raise self.error
        self.moments = list(moments)
        root = self.tmp / "cap"
        root.mkdir(exist_ok=True)
        frames = {i: [_chart(root / f"m{i}_0.jpg", blur=3), _chart(root / f"m{i}_1.jpg")] for i in range(len(moments))}
        return CaptureResult(frames=frames, tmp=root)


def _setup(fine_settings, fine_db, tmp_path, *, llm=None, capturer=None, meta=None):
    meta = meta or video_meta()
    t = Transcript(video_id=meta.video_id, language="it", source="x", segments=build_segments(btc_snippets(), 8, 14))
    analysis = postprocess_analysis(AnalysisResult.model_validate(analysis_for(t)), t, 8)
    ctx = make_ctx(fine_settings, fine_db, meta=meta, llm=llm, capturer=capturer)
    ctx.db.add_video(meta.video_id, source="manual")
    ws = Workspace(fine_settings.archive_dir / "Canale" / "video")
    return ctx, meta, ws, t, analysis


def _locate_responder(purpose, parts):
    video = parts[0]
    relevant = video.start_s < 60  # il grafico BTC sì, la slide (dopo il minuto 1) no
    return {"is_relevant": relevant, "best_offset_s": 2.0, "content_type": "PRICE_CHART",
            "on_screen": "Grafico BTCUSD giornaliero", "asset": "BTCUSD", "timeframe": "1D",
            "readings": [], "answer": "Linee a 60.000", "confidence": "HIGH"}


def test_visual_stages_happy_path(fine_settings, fine_db, tmp_path):
    llm = FakeProvider(responses={"locate": _locate_responder, "read": {
        "answer": "Supporto a 60.000", "asset": "BTCUSD", "timeframe": "1D",
        "readings": [{"label": "Supporto", "value": "60.000"}], "legibility": "HIGH", "notes": ""}})
    cap = FakeCapturer(tmp_path)
    ctx, meta, ws, t, analysis = _setup(fine_settings, fine_db, tmp_path, llm=llm, capturer=cap)
    report = run_visual_stages(ctx, meta, ws, t, analysis)
    chart = report.items[0]
    assert chart.capture_s == pytest.approx(chart.window_start_s + 2.0)
    assert cap.moments == [chart.capture_s]  # la slide scartata non viene scaricata
    assert chart.frame_file.startswith("frames/") and (ws.root / chart.frame_file).exists()
    assert chart.frame_file.endswith("_price_chart_BTCUSD.jpg")
    assert chart.read.readings[0].value == "60.000"
    assert report.items[1].dropped
    assert any("scartati" in n for n in report.notes)
    assert [c.purpose for c in llm.calls].count("locate") == 2 and [c.purpose for c in llm.calls].count("read") == 1
    assert not (tmp_path / "cap").exists()  # file temporanei rimossi


def test_visual_stages_degrade_when_youtube_blocks_download(fine_settings, fine_db, tmp_path):
    llm = FakeProvider(responses={"locate": _locate_responder})
    cap = FakeCapturer(tmp_path, error=BlockedError("Sign in to confirm you're not a bot"))
    ctx, meta, ws, t, analysis = _setup(fine_settings, fine_db, tmp_path, llm=llm, capturer=cap)
    report = run_visual_stages(ctx, meta, ws, t, analysis)
    assert report.items[0].capture_error and not report.items[0].frame_file
    assert any("Screenshot non scaricati" in n for n in report.notes)
    assert "read" not in [c.purpose for c in llm.calls]


def test_visual_stages_skip_locate_for_unlisted_and_survive_locate_errors(fine_settings, fine_db, tmp_path):
    cap = FakeCapturer(tmp_path)
    llm = FakeProvider(responses={"locate": TemporaryError("Gemini occupato")})
    ctx, meta, ws, t, analysis = _setup(fine_settings, fine_db, tmp_path, llm=llm, capturer=cap,
                                        meta=video_meta(availability="unlisted"))
    report = run_visual_stages(ctx, meta, ws, t, analysis)
    assert "locate" not in [c.purpose for c in llm.calls]
    assert any("solo video pubblici" in n for n in report.notes)
    assert all(i.frame_file for i in report.items)  # catturati al momento della trascrizione

    ctx2, meta2, ws2, t2, analysis2 = _setup(fine_settings, fine_db, tmp_path, llm=llm, capturer=FakeCapturer(tmp_path))
    report2 = run_visual_stages(ctx2, meta2, ws2, t2, analysis2)
    assert all(i.locate_error for i in report2.items)
    assert any("Localizza non riuscito" in n for n in report2.notes)
    assert all(i.frame_file for i in report2.items)


def test_pipeline_report_contains_screenshot(fine_settings, fine_db, tmp_path, fixed_now):
    from tests.test_pipeline import _analysis_responder
    from ytkb.pipeline.runner import Pipeline

    llm = FakeProvider(responses={"analysis": _analysis_responder, "locate": _locate_responder})
    ctx = make_ctx(fine_settings, fine_db, llm=llm, capturer=FakeCapturer(tmp_path), clock=lambda: fixed_now)
    row = Pipeline(ctx).process_now("dQw4w9WgXcQ")
    assert row.status == "done", row.last_error
    md = (Path(row.archive_dir) / "report.md").read_text(encoding="utf-8")
    assert "![Grafico di prezzo" in md and "frames/" in md
    html = (Path(row.archive_dir) / "report.html").read_text(encoding="utf-8")
    assert "data:image/jpeg;base64," in html  # immagine incorporata: l'HTML è autocontenuto


def test_visual_bug_does_not_fail_video(fine_settings, fine_db, tmp_path, fixed_now, monkeypatch):
    from tests.test_pipeline import _analysis_responder
    from ytkb.pipeline.runner import Pipeline

    def boom(*a, **k):
        raise ZeroDivisionError("bug di prova")

    monkeypatch.setattr("ytkb.visual.stage.run_visual_stages", boom)
    llm = FakeProvider(responses={"analysis": _analysis_responder})
    ctx = make_ctx(fine_settings, fine_db, llm=llm, capturer=FakeCapturer(tmp_path), clock=lambda: fixed_now)
    row = Pipeline(ctx).process_now("dQw4w9WgXcQ")
    assert row.status == "done"
    md = (Path(row.archive_dir) / "report.md").read_text(encoding="utf-8")
    assert "Riferimenti visivi non disponibili" in md
