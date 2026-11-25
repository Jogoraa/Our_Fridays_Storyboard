"""The one command: `uv run film`. Validates the storyboard, then runs each stage in order.

Every stage is cached, so a second run does nothing, and a storyboard edit regenerates only what it touches.
"""
from __future__ import annotations

import argparse
import json
import sys

from pipeline import assemble, music, narration, script, timing
from pipeline.common import OUTPUTS, ConfigError, ProviderError
from pipeline.validate import StoryboardError, load_storyboard

STAGES = ("validate", "script", "narration", "radio-cut")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="film", description="Regenerate the film 'Our Fridays' from storyboard.json.")
    parser.add_argument("--radio-cut", action="store_true", help="stop after the narration-only prototype")
    parser.add_argument("--only", choices=STAGES, help="run a single stage")
    parser.add_argument("--shot", metavar="ID", help="limit generation to one shot, e.g. shot_03")
    parser.add_argument("--lang", help="narration language to build (default: the storyboard's)")
    parser.add_argument("--one-take", action="store_true",
                        help="record all changed shots in one speech request and split at pauses (saves quota, less reliable)")
    parser.add_argument("--wait-for-quota", action="store_true",
                        help="when a free allowance runs out, wait as long as the provider asks and continue")
    parser.add_argument("--force", action="store_true", help="ignore the cache for the stages that run")
    return parser


def _timing(sb: dict, lang: str) -> dict:
    summary = OUTPUTS / "narration" / lang / "durations.json"
    if not summary.exists():
        raise timing.TimingError(f"no narration for '{lang}' yet; run the narration stage first")
    result = timing.build_timing(sb, json.loads(summary.read_text(encoding="utf-8")))
    timing.check_total(result)
    path = OUTPUTS / f"timing_{lang}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"  timing [{lang}]: {result['total']:.1f} s total")
    return result


def run(args: argparse.Namespace) -> None:
    print("validate")
    sb = load_storyboard()
    print(f"  storyboard ok: {len(sb['shots'])} shots, status {sb['project_status']}")
    lang = args.lang or sb["shots"][0]["narration"]["lang"]
    if args.only == "validate":
        return

    if args.only == "script":
        print("script")
        print(f"  proposal written to {script.run(sb, force=args.force)}")
        return

    if args.only in (None, "narration"):
        print("narration")
        narration.run(sb, lang=lang, only_shot=args.shot, force=args.force, batch=args.one_take, wait_for_quota=args.wait_for_quota)
        if args.only == "narration":
            return

    print("timing")
    plan = _timing(sb, lang)
    print("radio cut")
    bed = music.placeholder(plan["total"])
    assemble.radio_cut(sb, plan, lang=lang, music=bed, force=args.force and args.only == "radio-cut")
    if not args.radio_cut and args.only is None:
        print("keyframes, shots, score and final edit: stages not built yet")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run(args)
    except (ConfigError, StoryboardError, timing.TimingError, ProviderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
