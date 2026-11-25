"""Narration stage: one WAV file per shot.

The free speech quota is counted per request (10 a day on the main model), so when several shots
need recording the whole set is spoken in one request and cut at the pauses (pipeline/split.py).
A single changed line is still one small request for that shot alone.
"""
from __future__ import annotations

import array
import io
import json
import math
import statistics
import time
import wave
from collections.abc import Callable
from pathlib import Path

from pipeline import gemini
from pipeline.common import (
    OUTPUTS, RUNS_PATH, ProviderError, QuotaError, RetryableError,
    cache_key, call_with_retry, is_cached, rel, write_output,
)
from pipeline.split import SplitError, split_take
from pipeline.validate import StoryboardError

STAGE = "narration"
VERSION = "2"
MIN_SECONDS = 0.5
SILENCE_RMS = 50.0
BATCH_MIN = 3                      # fewer changed shots than this are recorded one by one
SEPARATOR = "\n\n<long pause>\n\n"  # spoken as a clear pause; this is where the take is cut
PACE_TOLERANCE = 1.3                # measured: honest takes stay within x1.18 of the median pace; a misplaced sentence does not

MAX_QUOTA_WAIT = 20 * 60           # never sit waiting longer than this for one slot
MAX_QUOTA_WAITS = 12

_exhausted: set[str] = set()       # models whose daily quota ran out during this run


def models() -> list[str]:
    """The voice model to use, then the lighter one with its own daily allowance."""
    return [gemini.TTS_MODEL, gemini.TTS_FALLBACK_MODEL]


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


def _check_clip(data: bytes) -> None:
    seconds, level = inspect_wav(data)
    if seconds < MIN_SECONDS:
        raise RetryableError(f"audio only {seconds:.2f} s long")
    if level < SILENCE_RMS:
        raise RetryableError(f"audio is silent (RMS {level:.1f})")


def _check_pace(clips: list[bytes], texts: list[str]) -> None:
    """After a split, every clip should take about as long per character as the others."""
    paces = [inspect_wav(clip)[0] / max(1, len(text)) for clip, text in zip(clips, texts)]
    median = statistics.median(paces)
    for index, pace in enumerate(paces):
        if not median / PACE_TOLERANCE <= pace <= median * PACE_TOLERANCE:
            raise RetryableError(f"split looks misaligned at line {index + 1} (pace {pace:.3f} vs median {median:.3f} s/char)")


def _with_model_fallback(make_call: Callable[[str], Callable[[], object]], **log) -> tuple[object, str]:
    """Try each voice model in turn; move on only when a model's daily quota is gone."""
    last: QuotaError | None = None
    for model in models():
        if model in _exhausted:
            continue
        try:
            return call_with_retry(make_call(model), model=model, **log), model
        except QuotaError as exc:
            _exhausted.add(model)
            last = exc
            print(f"  narration: daily quota used up on {model}")
    raise QuotaError(
        f"every voice model is out of quota; last error: {last}",
        retry_after=last.retry_after if last else None,
    )


def run(
    sb: dict,
    *,
    lang: str | None = None,
    only_shot: str | None = None,
    force: bool = False,
    batch: bool = False,
    wait_for_quota: bool = False,
    synth: Callable[..., bytes] | None = None,
    out_dir: Path | None = None,
    log_path: Path = RUNS_PATH,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, float]:
    """Generate missing or changed narration. Returns measured seconds per shot."""
    synth = synth or gemini.synthesize
    _exhausted.clear()
    lang = lang or sb["shots"][0]["narration"]["lang"]
    folder = (out_dir or OUTPUTS / "narration") / lang
    voice = sb["narration_voice"]["voice"]
    style = sb["narration_voice"]["style_instruction"]
    durations: dict[str, float] = {}
    todo: list[dict] = []

    for shot in sb["shots"]:
        if only_shot and shot["id"] != only_shot:
            continue
        text = text_for(shot, lang)
        # The key leaves the model out on purpose: a take from the fallback model is still a valid take.
        key = cache_key(STAGE, VERSION, {"text": text, "lang": lang, "voice": voice, "style_instruction": style})
        output = folder / f"{shot['id']}.wav"
        if not force and is_cached(output, key):
            durations[shot["id"]] = inspect_wav(output.read_bytes())[0]
            print(f"  narration {shot['id']} [{lang}]: cache hit")
        else:
            todo.append({"id": shot["id"], "text": text, "key": key, "output": output})

    def save(item: dict, data: bytes, model: str, mode: str) -> None:
        seconds = inspect_wav(data)[0]
        write_output(item["output"], data, item["key"],
                     {"shot": item["id"], "lang": lang, "seconds": round(seconds, 3), "model": model, "mode": mode})
        durations[item["id"]] = seconds
        print(f"  narration {item['id']} [{lang}]: {mode} take, {seconds:.2f} s ({model})")

    common_log = {"stage": STAGE, "provider": "gemini", "sleep": sleep, "log_path": log_path}

    if batch and len(todo) >= BATCH_MIN:
        texts = [item["text"] for item in todo]
        joined = SEPARATOR.join(texts)

        def batch_call(model: str) -> Callable[[], list[bytes]]:
            def call() -> list[bytes]:
                data = synth(joined, model=model, voice=voice, style_instruction=style)
                # Keep the raw take: if the split fails it can be studied without spending another request.
                raw = folder / "takes" / f"take_{model}_{int(time.time())}.wav"
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_bytes(data)
                try:
                    clips = split_take(data, len(todo), weights=[len(text) for text in texts])
                except SplitError as exc:
                    raise RetryableError(f"could not split the take: {exc}") from exc
                for clip in clips:
                    _check_clip(clip)
                _check_pace(clips, texts)
                return clips
            return call

        params = {"mode": "batch", "shots": [item["id"] for item in todo], "lang": lang, "voice": voice,
                  "style_instruction": style, "characters": len(joined)}
        try:
            clips, model = _with_model_fallback(
                batch_call, params=params, attempts=2,
                extra={"output": rel(folder), "cost_usd": 0.0}, **common_log,
            )
        except QuotaError:
            raise
        except ProviderError as exc:
            print(f"  narration: whole-film take failed ({str(exc)[:120]}); recording shot by shot")
        else:
            for item, clip in zip(todo, clips):
                save(item, clip, model, "batch")
            todo = []

    for item in todo:
        def single_call(model: str, text: str = item["text"]) -> Callable[[], bytes]:
            def call() -> bytes:
                data = synth(text, model=model, voice=voice, style_instruction=style)
                _check_clip(data)
                return data
            return call

        params = {"text": item["text"], "lang": lang, "voice": voice, "style_instruction": style}
        waits = 0
        while True:
            try:
                data, model = _with_model_fallback(
                    single_call, shot=item["id"], params=params,
                    extra={"output": rel(item["output"]), "cost_usd": 0.0}, **common_log,
                )
                break
            except QuotaError as exc:
                # The "per day" allowance is a rolling window: the provider says when a slot frees up.
                if not wait_for_quota or not exc.retry_after or exc.retry_after > MAX_QUOTA_WAIT or waits >= MAX_QUOTA_WAITS:
                    raise
                waits += 1
                print(f"  narration {item['id']}: out of quota, waiting {exc.retry_after / 60:.1f} min as the provider asks")
                sleep(exc.retry_after + 5.0)
                _exhausted.clear()
        save(item, data, model, "single")

    summary = folder / "durations.json"
    known = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    known.update({k: round(v, 3) for k, v in durations.items()})
    folder.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(dict(sorted(known.items())), indent=2) + "\n", encoding="utf-8")
    return durations
