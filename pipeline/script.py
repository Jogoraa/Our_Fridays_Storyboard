"""Script stage: draft the Amharic narration from the English lines, for a human to approve.

This stage never edits storyboard.json. It writes proposals; the author copies approved lines in.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from pipeline import gemini
from pipeline.common import rel, OUTPUTS, RUNS_PATH, ProviderError, cache_key, call_with_retry, is_cached, write_output

STAGE = "script"
VERSION = "2"
SYSTEM = (
    "You are an Ethiopian voice-over writer. Translate the English narration line into natural, "
    "warm, spoken Amharic for a storyteller reading aloud. Use everyday words and short sentences, "
    "keep the names Rahel (ራሄል) and Bekele (በቀለ), keep quoted speech as quoted speech, and keep "
    "the meaning and length close to the English. Reply with the Amharic line only, in Ge'ez script."
)


def models() -> list[str]:
    """The model to use, then the lighter one to fall back to when the first is overloaded."""
    return [gemini.TEXT_MODEL, gemini.TEXT_FALLBACK_MODEL]


def _draft(source: str, shot_id: str, output: Path, generate, sleep, log_path: Path) -> tuple[str, str]:
    last: ProviderError | None = None
    for model in models():
        try:
            text = call_with_retry(
                lambda model=model: generate(source, model=model, system_instruction=SYSTEM),
                stage=STAGE, shot=shot_id, provider="gemini", model=model, params={"source_en": source},
                sleep=sleep, log_path=log_path, extra={"output": rel(output), "cost_usd": 0.0},
            )
            return text, model
        except ProviderError as exc:
            last = exc
            print(f"  script {shot_id}: {model} unavailable, trying the next model")
    raise ProviderError(f"script {shot_id}: every text model failed; last error: {last}")


def run(
    sb: dict,
    *,
    force: bool = False,
    generate: Callable[..., str] | None = None,
    out_dir: Path | None = None,
    log_path: Path = RUNS_PATH,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    generate = generate or gemini.generate_text
    folder = out_dir or OUTPUTS / "script"
    rows = []
    for shot in sb["shots"]:
        source = shot["narration"]["source_en"]
        # The key leaves the model out on purpose: a line drafted by the fallback is still a valid draft.
        key = cache_key(STAGE, VERSION, {"source_en": source, "system": SYSTEM})
        output = folder / f"{shot['id']}.am.json"
        if not force and is_cached(output, key):
            print(f"  script {shot['id']}: cache hit")
        else:
            proposed, model = _draft(source, shot["id"], output, generate, sleep, log_path)
            record = {"shot": shot["id"], "source_en": source, "proposed_am": proposed, "model": model}
            write_output(output, json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"), key, {"model": model})
            print(f"  script {shot['id']}: drafted by {model}")
        rows.append(json.loads(output.read_text(encoding="utf-8")))

    proposal = folder / "proposal.md"
    lines = ["# Amharic narration proposal", "", "Drafted by Gemini. Not used until the author approves or edits each line.", ""]
    for row in rows:
        lines += [f"## {row['shot']}", "", f"English: {row['source_en']}", "", f"አማርኛ: {row['proposed_am']}", ""]
    proposal.write_text("\n".join(lines), encoding="utf-8")
    return proposal
