"""Smoke test: call each configured provider once and log the latency, before any real work."""
from __future__ import annotations

import json
import sys

from pipeline import gemini, narration
from pipeline.common import OUTPUTS, RUNS_PATH, ProviderError, call_with_retry, has_env


def _last_latency() -> float:
    last = RUNS_PATH.read_text(encoding="utf-8").strip().splitlines()[-1]
    return json.loads(last)["latency_s"]


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []
    folder = OUTPUTS / "smoke"
    folder.mkdir(parents=True, exist_ok=True)

    if has_env("GEMINI_API_KEY"):
        checks = [
            ("gemini text", gemini.TEXT_MODEL, {"prompt": "Reply with the single word: ready"},
             lambda: gemini.generate_text("Reply with the single word: ready")),
            ("gemini tts (en)", gemini.TTS_MODEL, {"text": "Every Friday.", "voice": "Sulafat"},
             lambda: gemini.synthesize("Every Friday.", voice="Sulafat", style_instruction="warm and calm")),
            ("gemini tts (am)", gemini.TTS_MODEL, {"text": "ሁልጊዜ አርብ።", "voice": "Sulafat"},
             lambda: gemini.synthesize("ሁልጊዜ አርብ።", voice="Sulafat", style_instruction="warm and calm")),
        ]
        for name, model, params, call in checks:
            try:
                result = call_with_retry(call, stage="smoke", provider="gemini", model=model, params=params, attempts=2)
            except ProviderError as exc:
                rows.append((name, model, "-", f"FAILED: {str(exc)[:160]}"))
                continue
            if isinstance(result, bytes):
                seconds, level = narration.inspect_wav(result)
                (folder / f"{name.replace(' ', '_').replace('(', '').replace(')', '')}.wav").write_bytes(result)
                detail = f"ok, {seconds:.2f} s of audio, RMS {level:.0f}"
            else:
                detail = f"ok, replied {result[:40]!r}"
            rows.append((name, model, f"{_last_latency():.2f} s", detail))
    else:
        rows.append(("gemini", "-", "-", "skipped: GEMINI_API_KEY is empty in .env"))

    for name, keys in (("cloudflare", ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")), ("kaggle", ("KAGGLE_USERNAME", "KAGGLE_KEY"))):
        missing = [k for k in keys if not has_env(k)]
        rows.append((name, "-", "-", f"skipped: {', '.join(missing)} empty in .env" if missing else "keys present; stage not built yet"))

    width = max(len(r[0]) for r in rows)
    for name, model, latency, detail in rows:
        print(f"{name:<{width}}  {model:<24} {latency:>8}  {detail}")
    return 1 if any("FAILED" in r[3] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
