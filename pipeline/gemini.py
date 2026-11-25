"""Gemini API calls over plain HTTP (Interactions API): text generation and text-to-speech.

Checked against the docs on 2026-11-25:
https://aistudio.google.com/docs/speech-generation and /docs/text-generation
"""
from __future__ import annotations

import base64
import os
import re

import httpx

from pipeline.common import ProviderError, QuotaError, RetryableError, require_env

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
TEXT_FALLBACK_MODEL = os.environ.get("GEMINI_TEXT_FALLBACK_MODEL", "gemini-3.5-flash-lite")
TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
TTS_FALLBACK_MODEL = os.environ.get("GEMINI_TTS_FALLBACK_MODEL", "gemini-3.8-flash-lite-tts")
TIMEOUT_SECONDS = 180.0


def retry_delay(message: str) -> float | None:
    """Read 'Please retry in 56m50s' from an error message. None if the provider gave no hint."""
    match = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", message)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def raise_for_status(status: int, text: str) -> None:
    """Sort a response into: fine, worth retrying, daily quota gone, or a request that will never work."""
    if status == 200:
        return
    if status == 429:
        if "per day" in text:
            raise QuotaError(f"HTTP 429: {text[:300]}", retry_after=retry_delay(text))
        raise RetryableError(f"HTTP 429: {text[:300]}", retry_after=retry_delay(text))
    if status >= 500:
        raise RetryableError(f"HTTP {status}: {text[:300]}")
    raise ProviderError(f"HTTP {status}: {text[:500]}")


def _post(body: dict) -> dict:
    headers = {"x-goog-api-key": require_env("GEMINI_API_KEY"), "Content-Type": "application/json"}
    try:
        response = httpx.post(ENDPOINT, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
    except httpx.TransportError as exc:
        raise RetryableError(f"network error: {type(exc).__name__}: {exc}") from exc
    raise_for_status(response.status_code, response.text)
    return response.json()


def _last_content(result: dict, kind: str) -> dict:
    blocks = [
        block
        for step in result.get("steps", [])
        if step.get("type") == "model_output"
        for block in step.get("content", [])
        if block.get("type") == kind
    ]
    if not blocks:
        raise RetryableError(f"response contained no {kind} output")
    return blocks[-1]


def generate_text(prompt: str, *, model: str = TEXT_MODEL, system_instruction: str | None = None) -> str:
    body: dict = {"model": model, "input": prompt, "store": False}
    if system_instruction:
        body["system_instruction"] = system_instruction
    return _last_content(_post(body), "text")["text"].strip()


def synthesize(text: str, *, model: str = TTS_MODEL, voice: str, style_instruction: str) -> bytes:
    """Return a complete WAV file (24 kHz, mono, 16-bit). The text is spoken verbatim."""
    annotation: dict = {"type": "speech_metadata"}
    if style_instruction:
        annotation["style"] = style_instruction
    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": text, "annotations": [annotation]}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
        "store": False,
    }
    data = base64.b64decode(_last_content(_post(body), "audio")["data"])
    if not data.startswith(b"RIFF"):
        raise RetryableError("TTS response was not a WAV file")
    return data
