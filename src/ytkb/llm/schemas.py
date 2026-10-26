"""Schemi degli output dei modelli (validati con Pydantic).

Le descrizioni dei campi vengono inviate al modello insieme allo schema: sono istruzioni, scritte in italiano.
Regola: niente campi "null" — si usano stringhe vuote e liste vuote (schemi più semplici, meno errori del modello).
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VideoType = Literal["OPERATIONAL_TRADING", "EDUCATIONAL_THEORY", "MACRO_ANALYSIS", "HYBRID", "OTHER"]
Bias = Literal["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]
LevelKind = Literal["SUPPORT", "RESISTANCE", "TARGET", "STOP", "ENTRY", "PIVOT", "OTHER"]
TriggerType = Literal["PRICE_CHART", "EDUCATIONAL_SLIDE", "INDICATOR_SETTINGS", "DATA_TABLE", "OTHER"]
Confidence = Literal["LOW", "MEDIUM", "HIGH"]


class _LLMModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------------------
# Analisi della trascrizione (stadio 3)
# --------------------------------------------------------------------------------------
class SegmentRange(_LLMModel):
    start_segment: int = Field(description="ID del primo segmento")
    end_segment: int = Field(description="ID dell'ultimo segmento (incluso)")
    reason: str = Field(default="", description="Perché questa parte vale la pena")


class WorthWatching(_LLMModel):
    score: int = Field(ge=1, le=5, description="1 = basta il riassunto … 5 = da guardare tutto")
    reason: str = Field(description="Motivo del punteggio, una o due frasi")
    best_ranges: list[SegmentRange] = Field(default_factory=list, description="Le parti da guardare, se ce ne sono")


class PriceLevel(_LLMModel):
    value: float = Field(description="Il prezzo/livello come numero (es. 60000, 1.085, 5821.5)")
    kind: LevelKind
    note: str = Field(default="", description="Breve nota, es. 'chiusura daily sotto = invalidazione'")
    segment_id: int = Field(description="ID del segmento in cui il numero viene pronunciato")
    spoken_text: str = Field(description="Parole ESATTE della trascrizione che contengono il numero (5-12 parole)")


class AssetView(_LLMModel):
    asset: str = Field(description="Ticker normalizzato: BTCUSD, ETHUSD, SPX, NDX, DAX, FTSEMIB, XAUUSD, EURUSD, NVDA…")
    asset_name: str = Field(default="", description="Nome leggibile, es. 'Bitcoin', 'S&P 500'")
    timeframe: str = Field(default="", description="Es. '1D', '4H', 'settimanale'; vuoto se non detto")
    bias: Bias
    thesis: str = Field(description="La tesi dell'autore su questo asset, 1-3 frasi")
    levels: list[PriceLevel] = Field(default_factory=list)
    invalidation: str = Field(default="", description="Cosa invaliderebbe la tesi, se detto")
    trade_idea: str = Field(default="", description="Setup operativo esplicitamente proposto dall'autore; vuoto se assente")
    segment_ids: list[int] = Field(default_factory=list, description="Segmenti in cui si parla di questo asset")


class Concept(_LLMModel):
    title: str
    explanation: str = Field(description="Spiegazione completa ma concisa")
    steps: list[str] = Field(default_factory=list, description="Regole o passaggi del metodo, se presenti")
    examples: list[str] = Field(default_factory=list, description="Esempi pratici, formule, impostazioni citate")
    segment_ids: list[int] = Field(default_factory=list)


class MacroPoint(_LLMModel):
    topic: str = Field(description="Es. 'Inflazione USA', 'BCE', 'Mercato del lavoro'")
    view: str = Field(description="Visione dell'autore")
    upcoming_events: list[str] = Field(default_factory=list, description="Eventi futuri citati, con data se detta")
    segment_ids: list[int] = Field(default_factory=list)


class VisualTrigger(_LLMModel):
    start_segment: int
    end_segment: int
    trigger_type: TriggerType
    importance: int = Field(ge=1, le=5, description="5 = indispensabile per capire il contenuto")
    asset: str = Field(default="", description="Ticker se riguarda un asset, altrimenti vuoto")
    needs_video_clip: bool = Field(default=False, description="true solo se conta il movimento (replay, disegno live)")
    spoken_context: str = Field(description="Cosa dice l'autore in quel momento (parafrasi breve)")
    vision_question: str = Field(description="Domanda precisa da porre guardando lo schermo in quel momento")


class Chapter(_LLMModel):
    title: str
    start_segment: int


class AnalysisResult(_LLMModel):
    video_type: VideoType
    source_language: str = Field(description="Lingua parlata nel video, codice ISO (it, en…)")
    tldr: list[str] = Field(description="3-6 punti densi: il succo del video")
    summary: str = Field(description="Riassunto in un paragrafo di 4-8 frasi")
    worth_watching: WorthWatching
    assets: list[AssetView] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    macro: list[MacroPoint] = Field(default_factory=list)
    visual_triggers: list[VisualTrigger] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    sponsor_or_conflicts: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list, description="Incertezze: parti poco chiare, numeri o ticker dubbi")


# --------------------------------------------------------------------------------------
# Riferimenti visivi (stadi 4 e 6)
# --------------------------------------------------------------------------------------
class Reading(_LLMModel):
    label: str = Field(description="Cosa è, es. 'Resistenza', 'EMA 200', 'Prezzo attuale', 'Regola 1'")
    value: str = Field(description="Il valore/testo esattamente come appare a schermo, es. '64.480' o '1,0850'")


class LocateResult(_LLMModel):
    is_relevant: bool = Field(description="false se a schermo non c'è nulla di utile (solo webcam, transizione)")
    best_offset_s: float = Field(description="Secondi dall'INIZIO DELLA CLIP del momento in cui lo schermo è più chiaro")
    content_type: TriggerType
    on_screen: str = Field(description="Descrizione concreta di cosa si vede (strumento, timeframe, disegni, testo)")
    asset: str = Field(default="", description="Ticker visibile sul grafico, se c'è")
    timeframe: str = Field(default="", description="Timeframe visibile, se c'è")
    readings: list[Reading] = Field(default_factory=list, description="Valori leggibili con certezza a schermo")
    answer: str = Field(description="Risposta alla domanda richiesta")
    confidence: Confidence


class FrameReadResult(_LLMModel):
    answer: str = Field(description="Risposta precisa alla domanda, basata solo sull'immagine")
    asset: str = Field(default="")
    timeframe: str = Field(default="")
    readings: list[Reading] = Field(default_factory=list, description="Solo valori leggibili con certezza")
    legibility: Confidence = Field(description="Quanto sono leggibili testo e numeri")
    notes: str = Field(default="", description="Avvertenze: valori incerti, parti coperte, ecc.")


# --------------------------------------------------------------------------------------
# Trascrizione di riserva da link YouTube (stadio 2, fonte gemini_url)
# --------------------------------------------------------------------------------------
class TranscriptLine(_LLMModel):
    start_s: float = Field(description="Secondi dall'INIZIO DELLA CLIP")
    text: str


class GeminiTranscript(_LLMModel):
    language: str = Field(description="Codice ISO della lingua parlata")
    lines: list[TranscriptLine]


# --------------------------------------------------------------------------------------
# Conversione in JSON Schema per l'API
# --------------------------------------------------------------------------------------
_DROP_KEYS = {"title", "default", "examples"}


def response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema "semplice" per l'API: riferimenti risolti, niente titoli/default, tutte le proprietà richieste."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any, field_map: bool = False) -> Any:
        if isinstance(node, list):
            return [resolve(x) for x in node]
        if not isinstance(node, dict):
            return node
        if field_map:  # le chiavi sono nomi di campi (possono chiamarsi "title"!): non vanno filtrate
            return {k: resolve(v) for k, v in node.items()}
        if "allOf" in node and len(node["allOf"]) == 1:  # vecchio stile Pydantic: allOf con un solo $ref
            node = {**{k: v for k, v in node.items() if k != "allOf"}, **node["allOf"][0]}
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            target = copy.deepcopy(defs[name])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            node = {**target, **extra}
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _DROP_KEYS:
                continue
            out[key] = resolve(value, field_map=(key == "properties"))
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"].keys())
        return out

    return resolve(schema)
