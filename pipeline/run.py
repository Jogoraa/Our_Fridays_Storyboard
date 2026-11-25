"""The one command: `uv run film`. Validates the storyboard, then runs each stage in order.

Every stage is cached, so a second run does nothing, and a storyboard edit regenerates only what it touches.
"""
from __future__ import annotations

import argparse
import functools
import json
import sys

from pipeline import assemble, keyframes, music, narration, script, shots, timing
from pipeline.common import OUTPUTS, ConfigError, ProviderError
from pipeline.validate import StoryboardError, load_storyboard

STAGES = ("validate", "script", "narration", "radio-cut", "keyframes", "music", "shots", "film")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="film", description="Regenerate the film from storyboard.json.")
    parser.add_argument("--radio-cut", action="store_true", help="stop after the narration-only prototype")
    parser.add_argument("--only", choices=STAGES, help="run a single stage")
    parser.add_argument("--shot", metavar="ID", help="limit generation to one shot, e.g. shot_03")
    parser.add_argument("--lang", help="narration language to build (default: the storyboard's)")
    parser.add_argument("--aspect", choices=("9:16", "16:9"), help="build one aspect ratio only")
    parser.add_argument("--one-take", action="store_true",
                        help="record all changed shots in one speech request and split at pauses (saves quota, less reliable)")
    parser.add_argument("--wait-for-quota", action="store_true",
                        help="when a free allowance runs out, wait as long as the provider asks and continue")
    parser.add_argument("--collect", action="store_true",
                        help="do not start a new GPU job; collect the output of the one already pushed")
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
    print(f"  timing [{lang}]: {result['total']:.1f} s total (voice tempo {result['tempo']:g})")
    return result


def _score(sb: dict, total: float):
    """The chosen score if there is one, otherwise the placeholder bed (and say so)."""
    chosen = sb["music"].get("chosen")
    if chosen and (OUTPUTS / "music" / chosen).is_file():
        return OUTPUTS / "music" / chosen
    print("  music: no score chosen yet, using the placeholder bed")
    return music.placeholder(total)


def run(args: argparse.Namespace) -> None:
    only = args.only

    def wants(stage: str) -> bool:
        return only in (None, stage)

    print("validate")
    sb = load_storyboard()
    print(f"  storyboard ok: {len(sb['shots'])} shots, status {sb['project_status']}")
    lang = args.lang or sb["shots"][0]["narration"]["lang"]
    if only == "validate":
        return

    if only == "script":
        print("script")
        print(f"  proposal written to {script.run(sb, force=args.force)}")
        return

    if wants("narration"):
        print("narration")
        narration.run(sb, lang=lang, only_shot=args.shot, force=args.force and only == "narration",
                      batch=args.one_take, wait_for_quota=args.wait_for_quota)
        if only == "narration":
            return

    if only != "keyframes":
        print("timing")
        plan = _timing(sb, lang)

    if args.radio_cut or only == "radio-cut":
        print("radio cut")
        assemble.radio_cut(sb, plan, lang=lang, music=music.placeholder(plan["total"]),
                           force=args.force and only == "radio-cut")
        return

    if wants("keyframes"):
        print("keyframes")
        runner = functools.partial(keyframes.kaggle_runner, push=not args.collect)
        keyframes.run(sb, only_shot=args.shot, force=args.force and only == "keyframes", runner=runner)
        if only == "keyframes":
            return

    if only == "music":
        print("music")
        runner = functools.partial(music.kaggle_runner, push=not args.collect)
        for path in music.candidates(sb, plan["total"], force=args.force, runner=runner):
            print(f"  candidate: {path.name}")
        return

    aspects = [args.aspect] if args.aspect else [f["aspect_ratio"] for f in sb["formats"]]
    print("shots")
    clips = {
        aspect: shots.render(sb, plan, aspect, only_shot=args.shot if only == "shots" else None,
                             force=args.force and only == "shots")
        for aspect in aspects
    }
    if only == "shots":
        return

    print("film")
    score = _score(sb, plan["total"])
    for aspect in aspects:
        assemble.film(sb, plan, lang=lang, aspect=aspect, music=score, clips=clips[aspect],
                      name=sb.get("slug", "film"), force=args.force and only == "film")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Amharic in messages must not crash a Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    try:
        run(args)
    except (ConfigError, StoryboardError, timing.TimingError, ProviderError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
