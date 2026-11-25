"""Validate storyboard.json: JSON Schema first, then the checks a schema cannot express."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
STORYBOARD_PATH = ROOT / "storyboard.json"
SCHEMA_PATH = ROOT / "schema" / "storyboard.schema.json"

MIN_SECONDS = 60.0
MAX_SECONDS = 90.0


class StoryboardError(Exception):
    """The storyboard breaks the contract. The message says where and why."""


def _schema_errors(sb: dict) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(sb), key=lambda e: [str(p) for p in e.absolute_path]
    )
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}" for e in errors]


def _semantic_errors(sb: dict) -> list[str]:
    errors: list[str] = []
    known = {c["id"] for c in sb["characters"]}
    ids = [s["id"] for s in sb["shots"]]

    for shot_id in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"shot id {shot_id} is used more than once")
    if ids != sorted(ids):
        errors.append(f"shots are out of order: {', '.join(ids)}")

    for shot in sb["shots"]:
        for character in shot["characters"]:
            if character not in known:
                errors.append(f"{shot['id']}: unknown character '{character}'")

    for cue in sb["music"]["cues"]:
        if cue["at_shot"] not in ids:
            errors.append(f"music cue points at unknown shot '{cue['at_shot']}'")

    ratios = {f["aspect_ratio"] for f in sb["formats"]}
    if ratios != {"9:16", "16:9"}:
        errors.append("formats must contain exactly 9:16 and 16:9")

    total = sum(s["duration_seconds"] for s in sb["shots"]) + sb["end_card"]["duration_seconds"]
    if not MIN_SECONDS <= total <= MAX_SECONDS:
        errors.append(
            f"planned shots plus end card total {total:g} s; the film must be "
            f"{MIN_SECONDS:g}-{MAX_SECONDS:g} s"
        )
    return errors


def validate_storyboard(sb: dict) -> None:
    errors = _schema_errors(sb)
    if not errors:
        errors = _semantic_errors(sb)
    if errors:
        raise StoryboardError("storyboard.json is invalid:\n  - " + "\n  - ".join(errors))


def load_storyboard(path: Path | None = None) -> dict:
    path = path or STORYBOARD_PATH
    try:
        sb = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StoryboardError(f"{path} not found") from None
    except json.JSONDecodeError as exc:
        raise StoryboardError(f"{path.name} is not valid JSON: {exc}") from None
    validate_storyboard(sb)
    return sb
