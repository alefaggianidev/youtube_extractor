import yaml

from tests.helpers import analysis_for, btc_snippets, video_meta
from ytkb.llm.schemas import AnalysisResult
from ytkb.models import Transcript
from ytkb.pipeline.postprocess import postprocess_analysis
from ytkb.report.render import render_html, render_markdown
from ytkb.report.viewmodel import build_report_vm
from ytkb.youtube.transcripts import build_segments


def _vm(settings, **meta_overrides):
    meta = video_meta(**meta_overrides)
    t = Transcript(video_id=meta.video_id, language="it", source="transcript_api",
                   segments=build_segments(btc_snippets(), 8, 14))
    a = postprocess_analysis(AnalysisResult.model_validate(analysis_for(t)), t, 8)
    return build_report_vm(meta, t, a, None, settings), t


def test_markdown_report_content(settings):
    vm, t = _vm(settings)
    md = render_markdown(vm)
    assert md.startswith("---\n")
    front = yaml.safe_load(md.split("---\n")[1])
    assert front["video_id"] == "dQw4w9WgXcQ" and front["assets"] == ["BTCUSD", "SPX"]
    assert front["bias"]["BTCUSD"] == "bullish"
    assert "## ⚡ In 30 secondi" in md
    assert "★★★☆☆ (3/5)" in md
    assert "| **60.000** | Supporto | 🗣️ detto a voce |" in md
    assert "| **64.480** | Resistenza | 🤖 non verificato |" in md
    seg = next(s for s in t.segments if "60.000 dollari" in s.text)
    assert f"https://youtu.be/dQw4w9WgXcQ?t={int(seg.start)}" in md
    assert "Sponsor / conflitto di interessi" in md
    assert "non è una raccomandazione di investimento" in md
    assert "Report dimostrativo" not in md


def test_html_report_is_escaped_and_selfcontained(settings):
    vm, _ = _vm(settings, title="Titolo <script>alert(1)</script> & co")
    html = render_html(vm)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "prefers-color-scheme: dark" in html
    assert 'class="bias bias-BULLISH"' in html


def test_markdown_table_cells_are_safe(settings):
    vm, _ = _vm(settings)
    vm.assets[0].levels[0].note = "nota | con barra\ne a capo"
    md = render_markdown(vm)
    assert "nota \\| con barra e a capo" in md


def test_link_text_is_escaped(settings):
    from ytkb.report.render import md_link_text

    assert md_link_text("[LIVE] Apertura | mercati") == "\\[LIVE\\] Apertura \\| mercati"
    vm, _ = _vm(settings)
    vm.chapters[0].label = "00:00 — [Intro] parte 1"
    assert "- [00:00 — \\[Intro\\] parte 1](" in render_markdown(vm)
