"""Narration stage: one TTS call and one WAV file per shot, so a re-take costs one call."""
from __future__ import annotations

import array
import io
import json
import math
import time
import wave
from collections.abc import Callable
from pathlib import Path

from pipeline import gemini
from pipeline.common import rel, OUTPUTS, RUNS_PATH, RetryableError, cache_key, call_with_retry, is_cached, write_output
from pipeline.validate import StoryboardError

STAGE = "narration"
VERSION = "1"
MIN_SECONDS = 0.5
SILENCE_RMS = 50.0


def text_for(shot: dict, lang: str) -> str:
    narration = shot["narration"]
    if lang == narration["lang"]:
        return narration["text"]
    if lang == "en":
        return narration["source_en"]
    raise StoryboardError(f"{shot['id']} has no narration in '{lang}' (it has '{narration['lang']}' and 'en')")


def inspect_wav(data: bytes) -> tuple[float, float]:
    """Return (seconds, RMS level) of a 16-bit WAV. Used to reject empty or silent takes."""
    with wave.open(io.BytesIO(data), "rb") as handle:
        frames = handle.getnframes()
        seconds = frames / handle.getframerate()
        samples = array.array("h", handle.readframes(frames))
    if not samples:
        return seconds, 0.0
    return seconds, math.sqrt(sum(s * s for s in samples) / len(samples))


def run(
    sb: dict,
    *,
    lang: str | None = None,
    only_shot: str | None = None,
    force: bool = False,
    synth: Callable[..., bytes] | None = None,
    out_dir: Path | None = None,
    log_path: Path = RUNS_PATH,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, float]:
    """Generate missing or changed narration. Returns measured seconds per shot."""
    synth = synth or gemini.synthesize
    lang = lang or sb["shots"][0]["narration"]["lang"]
    folder = (out_dir or OUTPUTS / "narration") / lang
    voice = sb["narration_voice"]["voice"]
    style = sb["narration_voice"]["style_instruction"]
    model = gemini.TTS_MODEL
    durations: dict[str, float] = {}

    for shot in sb["shots"]:
        shot_id = shot["id"]
        if only_shot and shot_id != only_shot:
            continue
        text = text_for(shot, lang)
        params = {"text": text, "lang": lang, "voice": voice, "style_instruction": style}
        key = cache_key(STAGE, VERSION, {"model": model, **params})
        output = folder / f"{shot_id}.wav"

        if not force and is_cached(output, key):
            durations[shot_id] = inspect_wav(output.read_bytes())[0]
            print(f"  narration {shot_id} [{lang}]: cache hit")
            continue

        def take(text: str = text) -> bytes:
            data = synth(text, model=model, voice=voice, style_instruction=style)
            seconds, level = inspect_wav(data)
            if seconds < MIN_SECONDS:
                raise RetryableError(f"audio only {seconds:.2f} s long")
            if level < SILENCE_RMS:
                raise RetryableError(f"audio is silent (RMS {level:.1f})")
            return data

        data = call_with_retry(
            take, stage=STAGE, shot=shot_id, provider="gemini", model=model, params=params,
            sleep=sleep, log_path=log_path, extra={"output": rel(output), "cost_usd": 0.0},
        )
        seconds = inspect_wav(data)[0]
        write_output(output, data, key, {"shot": shot_id, "lang": lang, "seconds": round(seconds, 3), "model": model})
        durations[shot_id] = seconds
        print(f"  narration {shot_id} [{lang}]: generated {seconds:.2f} s")

    summary = folder / "durations.json"
    known = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    known.update({k: round(v, 3) for k, v in durations.items()})
    folder.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(dict(sorted(known.items())), indent=2) + "\n", encoding="utf-8")
    return durations
