"""Risultati degli stadi visivi (4 localizza, 5 cattura, 6 lettura), salvati in ``visual.json``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ytkb.llm.schemas import FrameReadResult, LocateResult, VisualTrigger


class VisualItem(BaseModel):
    index: int
    trigger: VisualTrigger
    window_start_s: float
    window_end_s: float
    capture_s: float  # secondo scelto per lo screenshot
    locate: LocateResult | None = None
    locate_error: str = ""
    frame_file: str = ""  # percorso relativo alla cartella del video, es. frames/13m18s_price_chart_BTCUSD.jpg
    clip_file: str = ""
    capture_error: str = ""
    read: FrameReadResult | None = None
    read_error: str = ""

    @property
    def dropped(self) -> bool:
        """Scartato da "localizza" perché a schermo non c'era nulla di utile."""
        return self.locate is not None and not self.locate.is_relevant


class VisualReport(BaseModel):
    items: list[VisualItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
