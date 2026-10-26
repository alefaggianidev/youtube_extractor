"""Rigenera il report di esempio in documentazione/esempio-report/ a partire dai dati di prova dei test.

Uso:  uv run python scripts/genera_report_esempio.py

Il video, il canale e i numeri sono inventati: servono solo a mostrare com'è fatto un report.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402
from tests.helpers import analysis_for, btc_snippets, video_meta  # noqa: E402

from ytkb.config import load_settings  # noqa: E402
from ytkb.llm.schemas import AnalysisResult, FrameReadResult, LocateResult, Reading  # noqa: E402
from ytkb.models import Transcript  # noqa: E402
from ytkb.pipeline.postprocess import postprocess_analysis  # noqa: E402
from ytkb.report.render import write_reports  # noqa: E402
from ytkb.report.viewmodel import build_report_vm  # noqa: E402
from ytkb.utils.fs import atomic_write_text  # noqa: E402
from ytkb.visual.models import VisualItem, VisualReport  # noqa: E402
from ytkb.youtube.transcripts import build_segments  # noqa: E402

OUT = ROOT / "documentazione" / "esempio-report"
VIDEO_ID = "ESEMPIO0001"  # ID finto: i link non portano a un video reale


def fake_chart(path: Path) -> None:
    """Disegna un finto grafico a candele con due livelli orizzontali (al posto di uno screenshot vero)."""
    img = Image.new("RGB", (1920, 1080), (19, 23, 34))
    d = ImageDraw.Draw(img)
    random.seed(7)
    x, y = 60, 640
    for _ in range(64):
        o, c = y, y + random.randint(-38, 34)
        hi, lo = min(o, c) - random.randint(5, 30), max(o, c) + random.randint(5, 30)
        col = (38, 166, 154) if c < o else (239, 83, 80)
        d.line([(x + 8, hi), (x + 8, lo)], fill=col, width=2)
        d.rectangle([x, min(o, c), x + 16, max(o, c)], fill=col)
        x, y = x + 28, max(420, min(760, c))
    for level, ypos, col in (("60.000", 700, (255, 235, 59)), ("64.480", 380, (255, 152, 0))):
        d.line([(0, ypos), (1920, ypos)], fill=col, width=3)
        d.rectangle([1790, ypos - 18, 1920, ypos + 18], fill=col)
        d.text((1805, ypos - 8), level, fill=(0, 0, 0))
    d.text((40, 30), "BTCUSD · 1D · ESEMPIO", fill=(200, 200, 200))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=85)


def main() -> None:
    settings = load_settings(ROOT)
    meta = video_meta(id=VIDEO_ID, webpage_url=f"https://www.youtube.com/watch?v={VIDEO_ID}",
                      title="ESEMPIO — BTC e S&P500: settimana decisiva?")
    t = Transcript(video_id=VIDEO_ID, language="it", source="transcript_api",
                   segments=build_segments(btc_snippets(), 8, 14))
    analysis = postprocess_analysis(AnalysisResult.model_validate(analysis_for(t)), t, 8)
    analysis.assets[0].levels[2].note = "esempio: numero che NON compare nella trascrizione"
    frame = "frames/00m22s_price_chart_BTCUSD.jpg"
    fake_chart(OUT / frame)
    chart = VisualItem(
        index=0, trigger=analysis.visual_triggers[0], window_start_s=19, window_end_s=34, capture_s=22,
        locate=LocateResult(is_relevant=True, best_offset_s=3, content_type="PRICE_CHART",
                            on_screen="Grafico giornaliero BTCUSD su TradingView con due linee orizzontali",
                            asset="BTCUSD", timeframe="1D", answer="Supporto e resistenza disegnati",
                            confidence="HIGH"),
        frame_file=frame,
        read=FrameReadResult(answer="Linea gialla a 60.000 (supporto) e arancione a 64.480 (resistenza)",
                             asset="BTCUSD", timeframe="1D",
                             readings=[Reading(label="Supporto", value="60.000"),
                                       Reading(label="Resistenza", value="64.480")],
                             legibility="HIGH"),
    )
    slide = VisualItem(
        index=1, trigger=analysis.visual_triggers[1], window_start_s=98, window_end_s=110, capture_s=104,
        capture_error="download bloccato da YouTube",
        locate=LocateResult(is_relevant=True, best_offset_s=5, content_type="EDUCATIONAL_SLIDE",
                            on_screen="Slide con tre regole numerate",
                            answer="1) due minimi 2) più tocchi 3) conferma in chiusura", confidence="MEDIUM"),
    )
    visual = VisualReport(items=[chart, slide], notes=["1 screenshot non scaricato: c'è il link al secondo esatto."])
    vm = build_report_vm(meta, t, analysis, visual, settings, OUT)
    write_reports(vm, OUT)
    atomic_write_text(OUT / "transcript.txt", f"{meta.title}\n\n{t.to_readable()}\n")
    print(f"Report di esempio scritto in {OUT}")


if __name__ == "__main__":
    main()
