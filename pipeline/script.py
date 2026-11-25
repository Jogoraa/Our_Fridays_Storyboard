"""Script stage: draft the Amharic narration from the English lines, for a human to approve.

This stage never edits storyboard.json. It writes proposals; the author copies approved lines in.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from pipeline import gemini
from pipeline.common import OUTPUTS, RUNS_PATH, cache_key, call_with_retry, is_cached, write_output

STAGE = "script"
VERSION = "1"
SYSTEM = (
    "You are an Ethiopian voice-over writer. Translate the English narration line into natural, "
    "warm, spoken Amharic for a storyteller reading aloud. Use everyday words and short sentences, "
    "keep the names Rahel (ራሄል) and Bekele (በቀለ), keep quoted speech as quoted speech, and keep "
    "the meaning and length close to the English. Reply with the Amharic line only, in Ge'ez script."
)


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
    model = gemini.TEXT_MODEL
    rows = []
    for shot in sb["shots"]:
        source = shot["narration"]["source_en"]
        params = {"source_en": source, "system": SYSTEM}
        key = cache_key(STAGE, VERSION, {"model": model, **params})
        output = folder / f"{shot['id']}.am.json"
        if not force and is_cached(output, key):
            print(f"  script {shot['id']}: cache hit")
        else:
            proposed = call_with_retry(
                lambda source=source: generate(source, model=model, system_instruction=SYSTEM),
                stage=STAGE, shot=shot["id"], provider="gemini", model=model, params={"source_en": source},
                sleep=sleep, log_path=log_path, extra={"output": output.as_posix(), "cost_usd": 0.0},
            )
            record = {"shot": shot["id"], "source_en": source, "proposed_am": proposed}
            write_output(output, json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"), key, {"model": model})
            print(f"  script {shot['id']}: drafted")
        rows.append(json.loads(output.read_text(encoding="utf-8")))

    proposal = folder / "proposal.md"
    lines = ["# Amharic narration proposal", "", "Drafted by Gemini. Not used until the author approves or edits each line.", ""]
    for row in rows:
        lines += [f"## {row['shot']}", "", f"English: {row['source_en']}", "", f"አማርኛ: {row['proposed_am']}", ""]
    proposal.write_text("\n".join(lines), encoding="utf-8")
    return proposal
