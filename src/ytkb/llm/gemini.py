"""Provider Gemini tramite la Interactions API dell'SDK ``google-genai`` (D-002).

- output strutturato con JSON Schema (``response_format``);
- link YouTube passati come ``video`` con eventuale ritaglio (``processing.start_offset/end_offset``);
- tier ``flex`` (metà prezzo) con ripiego su ``standard`` in caso di errore temporaneo (D-017);
- un secondo tentativo se il JSON restituito non è valido.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import ValidationError

from ytkb.config import LLMSettings
from ytkb.llm.base import (
    ImagePart,
    LLMOutputError,
    LLMRequestError,
    LLMResponse,
    LLMTemporaryError,
    LLMUsage,
    Part,
    T,
    TextPart,
    VideoUrlPart,
)
from ytkb.llm.costs import estimate_cost
from ytkb.llm.schemas import response_schema

log = logging.getLogger(__name__)

_TEMPORARY_STATUS = {408, 409, 429, 500, 502, 503, 504}
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _offset(seconds: float) -> str:
    return f"{max(0.0, float(seconds)):.1f}s"


def build_input(parts: Sequence[Part]) -> list[dict[str, Any]]:
    """Converte le nostre ``Part`` nel formato della Interactions API."""
    items: list[dict[str, Any]] = []
    for p in parts:
        if isinstance(p, TextPart):
            items.append({"type": "text", "text": p.text})
        elif isinstance(p, ImagePart):
            items.append({"type": "image", "mime_type": p.mime_type, "resolution": p.resolution,
                          "data": base64.b64encode(p.data).decode("ascii")})
        elif isinstance(p, VideoUrlPart):
            item: dict[str, Any] = {"type": "video", "uri": p.url}
            processing: dict[str, Any] = {}
            if p.start_s is not None:
                processing["start_offset"] = _offset(p.start_s)
            if p.end_s is not None:
                processing["end_offset"] = _offset(p.end_s)
            if p.fps is not None:
                processing["fps"] = float(p.fps)
            if processing:
                item["processing"] = {"type": "static", **processing}
            if p.resolution:
                item["resolution"] = p.resolution
            items.append(item)
        else:  # pragma: no cover - difesa
            raise TypeError(f"Parte non supportata: {type(p)}")
    return items


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _clean_json(text: str) -> str:
    return _FENCE.sub("", (text or "").strip()).strip()


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, settings: LLMSettings, client: Any | None = None):
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
                timeout=int(settings.request_timeout_s * 1000)))
        self._client = client
        self._settings = settings

    # ------------------------------------------------------------------------------
    def _usage(self, interaction: Any, model: str, tier: str, has_youtube: bool) -> LLMUsage:
        u = getattr(interaction, "usage", None)
        input_tokens = int(getattr(u, "total_input_tokens", 0) or 0)
        output_tokens = int(getattr(u, "total_output_tokens", 0) or 0)
        thought_tokens = int(getattr(u, "total_thought_tokens", 0) or 0)
        video_tokens = 0
        if has_youtube and u is not None:
            for m in getattr(u, "input_tokens_by_modality", None) or []:
                if str(getattr(m, "modality", "")).lower() in ("video", "audio"):
                    video_tokens += int(getattr(m, "tokens", 0) or 0)
        cost = estimate_cost(model=model, service_tier=tier, input_tokens=input_tokens, output_tokens=output_tokens,
                             thought_tokens=thought_tokens, youtube_tokens=video_tokens, llm=self._settings)
        return LLMUsage(model=model, service_tier=tier, input_tokens=input_tokens, output_tokens=output_tokens,
                        thought_tokens=thought_tokens, video_tokens=video_tokens, cost_usd=cost)

    def _call(self, *, model: str, system: str, items: list[dict[str, Any]], schema: dict[str, Any],
              max_output_tokens: int, tier: str) -> Any:
        return self._client.interactions.create(
            model=model,
            system_instruction=system,
            input=items,
            response_format={"type": "text", "mime_type": "application/json", "schema": schema},
            response_mime_type="application/json",
            generation_config={"thinking_level": self._settings.thinking_level,
                               "max_output_tokens": max_output_tokens},
            service_tier=tier,
            timeout=self._settings.request_timeout_s,
        )

    def _classify(self, exc: BaseException, usage: LLMUsage | None) -> Exception:
        code = _status_code(exc)
        msg = f"{type(exc).__name__}: {str(exc)[:500]}"
        if isinstance(exc, httpx.TimeoutException | httpx.NetworkError) or code is None or code in _TEMPORARY_STATUS:
            return LLMTemporaryError(f"Gemini temporaneamente non disponibile ({msg})", usage)
        if code in (401, 403):
            return LLMRequestError(f"Gemini rifiuta la chiave API o il permesso ({msg})", usage)
        if code == 404:
            return LLMRequestError(f"Modello o risorsa Gemini inesistente: controlla llm.models ({msg})", usage)
        return LLMRequestError(f"Richiesta rifiutata da Gemini ({msg})", usage)

    # ------------------------------------------------------------------------------
    def generate(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        parts: Sequence[Part],
        schema: type[T],
        max_output_tokens: int | None = None,
    ) -> LLMResponse[T]:
        items = build_input(parts)
        json_schema = response_schema(schema)
        has_youtube = any(isinstance(p, VideoUrlPart) for p in parts)
        max_tokens = max_output_tokens or self._settings.max_output_tokens
        tier = self._settings.service_tier
        total: LLMUsage | None = None
        last_problem = ""
        tier_fallback_used = False
        for attempt in range(1, 3):  # al massimo 2 risposte "non valide"
            while True:
                try:
                    interaction = self._call(model=model, system=system, items=items, schema=json_schema,
                                             max_output_tokens=max_tokens, tier=tier)
                    break
                except Exception as exc:  # noqa: BLE001 - l'SDK solleva tipi diversi
                    err = self._classify(exc, total)
                    if (isinstance(err, LLMTemporaryError) and tier == "flex" and not tier_fallback_used
                            and self._settings.flex_fallback_to_standard):
                        log.info("[%s] tier flex non disponibile (%s): riprovo con standard", purpose, exc)
                        tier, tier_fallback_used = "standard", True
                        continue
                    raise err from exc
            usage = self._usage(interaction, model, tier, has_youtube)
            total = usage if total is None else total.add(usage)
            status = str(getattr(interaction, "status", "completed"))
            text = _clean_json(getattr(interaction, "output_text", "") or "")
            if status in ("failed", "cancelled"):
                raise LLMTemporaryError(f"Interazione Gemini terminata con stato '{status}'", total)
            if status == "budget_exceeded":
                raise LLMRequestError("Gemini: budget del progetto esaurito", total)
            try:
                data = schema.model_validate_json(text)
                if attempt > 1:
                    log.info("[%s] output valido al tentativo %d", purpose, attempt)
                return LLMResponse(data=data, usage=total, raw_text=text)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_problem = f"stato={status}; {str(exc)[:400]}"
                log.warning("[%s] JSON non valido (tentativo %d): %s", purpose, attempt, last_problem)
                if status == "incomplete":  # probabilmente troncato: più spazio al secondo giro
                    max_tokens = min(max_tokens * 2, 65536)
        raise LLMOutputError(f"Output del modello non valido dopo 2 tentativi: {last_problem}", total)
