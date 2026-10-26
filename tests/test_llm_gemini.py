"""Contratto con la Interactions API di Gemini, verificato intercettando le richieste HTTP (nessuna rete)."""

import json

import httpx
import pytest
from google import genai
from google.genai import types

from ytkb.config import LLMSettings
from ytkb.llm.base import ImagePart, LLMOutputError, LLMRequestError, TextPart, VideoUrlPart
from ytkb.llm.gemini import GeminiProvider, build_input
from ytkb.llm.schemas import LocateResult, response_schema


def _ok_body(payload: dict, usage: dict | None = None) -> dict:
    return {"id": "int_1", "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}],
            "usage": usage or {"total_input_tokens": 6000, "total_output_tokens": 300, "total_thought_tokens": 100,
                               "input_tokens_by_modality": [{"modality": "text", "tokens": 200},
                                                            {"modality": "video", "tokens": 5200},
                                                            {"modality": "audio", "tokens": 600}]}}


LOCATE = {"is_relevant": True, "best_offset_s": 9, "content_type": "PRICE_CHART",
          "on_screen": "Grafico giornaliero BTCUSD", "asset": "BTCUSD", "timeframe": "1D",
          "readings": [{"label": "Supporto", "value": "60.000"}], "answer": "Linea a 60.000", "confidence": "HIGH"}


def _provider(responses, settings: LLMSettings | None = None):
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        status, body = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, json=body)

    client = genai.Client(api_key="test", http_options=types.HttpOptions(
        httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_options=types.HttpRetryOptions(attempts=0, initial_delay=0.01, max_delay=0.02)))
    # nota: l'SDK fa comunque almeno 1 retry interno (verificato con google-genai 2.33)
    return GeminiProvider("test", settings or LLMSettings(), client=client), calls


def _locate_parts():
    return [VideoUrlPart("https://www.youtube.com/watch?v=dQw4w9WgXcQ", start_s=789, end_s=810, fps=1,
                         resolution="high"), TextPart("Descrivi lo schermo")]


def test_request_format_for_youtube_clip():
    provider, calls = _provider([(200, _ok_body(LOCATE))])
    resp = provider.generate(purpose="locate", model="gemini-3.8-flash", system="Sei un analista.",
                             parts=_locate_parts(), schema=LocateResult)
    body = calls[0]
    video = body["input"][0]["content"][0]
    assert video == {"type": "video", "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "high",
                     "processing": {"type": "static", "start_offset": "789.0s", "end_offset": "810.0s", "fps": 1.0}}
    assert body["service_tier"] == "flex"
    assert body["system_instruction"] == "Sei un analista."
    assert body["response_format"]["mime_type"] == "application/json"
    assert body["response_format"]["schema"]["required"]  # tutte le proprietà richieste
    assert body["generation_config"]["thinking_level"] == "low"
    assert resp.data.best_offset_s == 9 and resp.data.readings[0].value == "60.000"
    # costo: (6000 in * 0.75 + 400 out * 3.75) / 1e6, metà prezzo in flex
    assert resp.usage.video_tokens == 5800
    assert resp.usage.cost_usd == pytest.approx((6000 * 0.75 + 400 * 3.75) / 1e6 * 0.5)


def test_youtube_tokens_can_be_considered_free():
    provider, _ = _provider([(200, _ok_body(LOCATE))], LLMSettings(count_youtube_input_as_paid=False))
    resp = provider.generate(purpose="locate", model="gemini-3.8-flash", system="s", parts=_locate_parts(),
                             schema=LocateResult)
    assert resp.usage.cost_usd == pytest.approx((200 * 0.75 + 400 * 3.75) / 1e6 * 0.5)


def test_invalid_json_is_retried_once():
    bad = _ok_body({"is_relevant": True})  # mancano campi obbligatori
    provider, calls = _provider([(200, bad), (200, _ok_body(LOCATE))])
    resp = provider.generate(purpose="locate", model="gemini-3.8-flash", system="s", parts=_locate_parts(),
                             schema=LocateResult)
    assert len(calls) == 2 and resp.usage.calls == 2
    provider, calls = _provider([(200, bad), (200, bad)])
    with pytest.raises(LLMOutputError) as exc:
        provider.generate(purpose="locate", model="gemini-3.8-flash", system="s", parts=_locate_parts(),
                          schema=LocateResult)
    assert exc.value.usage is not None and exc.value.usage.calls == 2


def test_flex_falls_back_to_standard_on_429():
    busy = {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}}
    provider, calls = _provider([(429, busy), (429, busy), (200, _ok_body(LOCATE))])
    resp = provider.generate(purpose="locate", model="gemini-3.8-flash", system="s", parts=_locate_parts(),
                             schema=LocateResult)
    assert [c["service_tier"] for c in calls] == ["flex", "flex", "standard"]  # retry SDK, poi ripiego
    assert resp.usage.service_tier == "standard"


def test_permanent_errors_are_explained():
    missing = {"error": {"code": 404, "message": "models/gemini-9 not found", "status": "NOT_FOUND"}}
    provider, _ = _provider([(404, missing)])
    with pytest.raises(LLMRequestError, match="llm.models"):
        provider.generate(purpose="analysis", model="gemini-9", system="s", parts=[TextPart("x")],
                          schema=LocateResult)


def test_build_input_image_is_base64():
    items = build_input([ImagePart(b"\xff\xd8abc", resolution="high")])
    assert items[0]["type"] == "image" and items[0]["data"] == "/9hhYmM=" and items[0]["resolution"] == "high"


def test_response_schema_is_flat_and_keeps_field_named_title():
    from ytkb.llm.schemas import AnalysisResult

    schema = response_schema(AnalysisResult)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    concept = schema["properties"]["concepts"]["items"]
    assert "title" in concept["properties"]  # il campo "title" non deve sparire
    assert set(concept["required"]) == set(concept["properties"])
    assert schema["properties"]["video_type"]["enum"][0] == "OPERATIONAL_TRADING"
    assert "description" in schema["properties"]["tldr"]
