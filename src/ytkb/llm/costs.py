"""Stima dei costi a partire dai token (prezzi in ``llm.pricing`` della configurazione)."""

from __future__ import annotations

import logging

from ytkb.config import LLMSettings

log = logging.getLogger(__name__)
_warned: set[str] = set()

FLEX_DISCOUNT = 0.5  # il tier flex costa la metà (pagina prezzi Gemini, ottobre 2026)


def estimate_cost(
    *,
    model: str,
    service_tier: str,
    input_tokens: int,
    output_tokens: int,
    thought_tokens: int,
    youtube_tokens: int,
    llm: LLMSettings,
) -> float:
    price = llm.pricing.get(model)
    if price is None:
        # prova con il nome senza suffissi (es. "gemini-3.8-flash-001" -> "gemini-3.8-flash")
        price = next((p for name, p in llm.pricing.items() if model.startswith(name)), None)
    if price is None:
        if model not in _warned:
            _warned.add(model)
            log.warning("Prezzo sconosciuto per il modello %s: aggiungilo in llm.pricing per stimare i costi", model)
        return 0.0
    billable_input = input_tokens if llm.count_youtube_input_as_paid else max(0, input_tokens - youtube_tokens)
    cost = billable_input / 1e6 * price.input + (output_tokens + thought_tokens) / 1e6 * price.output
    if service_tier == "flex":
        cost *= FLEX_DISCOUNT
    return round(cost, 6)
