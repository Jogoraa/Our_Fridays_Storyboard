"""Music stage: score candidates from ACE-Step 1.5 on a Kaggle GPU, and a placeholder bed until one is chosen.

Like a composer's sketchbook: a few candidates from different seeds, one chosen by ear. The choice
and the reason are written into storyboard.json (music.chosen) and EXPERIMENTS.md.
"""
from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from pipeline import kaggle_jobs
from pipeline.common import OUTPUTS, ROOT, RUNS_PATH, ProviderError, cache_key, is_cached, log_run, mark_output, rel, run_ffmpeg

VERSION = "2"
MODEL = "acestep-v15-turbo"
STEPS = 8
CANDIDATE_SEEDS = (3101, 3102, 3103)
JOB_SCRIPT = ROOT / "gpu_jobs" / "acestep_score.py"
JOB_SLUG = "the-window-score"

# D major pad, below the voice's main energy, with a slow swell.
_PAD = (
    "0.10*(sin(2*PI*146.83*t)+0.8*sin(2*PI*220.00*t)+0.7*sin(2*PI*293.66*t)+0.35*sin(2*PI*369.99*t))"
    "*(0.65+0.35*sin(2*PI*0.08*t))"
)

Runner = Callable[[dict], tuple[Path, dict]]


def placeholder(duration: float, out_dir: Path | None = None) -> Path:
    """A placeholder bed so a cut is not dry. Deterministic FFmpeg synthesis, not a model, cached by length."""
    output = (out_dir or OUTPUTS / "music") / "placeholder.wav"
    seconds = round(duration + 1.0, 2)
    key = cache_key("music_placeholder", VERSION, {"seconds": seconds, "expr": _PAD})
    if is_cached(output, key):
        print("  music placeholder: cache hit")
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    fade_out = max(0.0, seconds - 3.0)
    run_ffmpeg([
        "-f", "lavfi", "-i", f"aevalsrc={_PAD}:s=48000:d={seconds}",
        "-af", f"lowpass=f=1400,aecho=0.6:0.5:120|240:0.3|0.2,afade=t=in:d=2,afade=t=out:st={fade_out}:d=3",
        "-ac", "2", "-c:a", "pcm_s16le", str(output),
    ])
    mark_output(output, key, {"kind": "placeholder", "seconds": seconds, "note": "FFmpeg synthesis, not a model"})
    print(f"  music placeholder: synthesised {seconds:.1f} s")
    return output


def candidate_path(seed: int, out_dir: Path | None = None) -> Path:
    return (out_dir or OUTPUTS / "music") / f"score_seed{seed}.flac"


def plan(sb: dict, duration: float, *, out_dir: Path | None = None, force: bool = False) -> list[dict]:
    music = sb["music"]
    seconds = int(round(duration + 6))  # a little longer than the film, so the edit can fade it out
    todo = []
    for seed in CANDIDATE_SEEDS:
        key = cache_key("music", VERSION, {
            "model": MODEL, "steps": STEPS, "caption": music["caption"], "bpm": music["tempo_bpm"],
            "key": music["key"], "duration": seconds, "seed": seed,
        })
        output = candidate_path(seed, out_dir)
        if force or not is_cached(output, key):
            todo.append({"file": output.name, "output": output, "key": key, "seed": seed, "duration": seconds})
    return todo


def kaggle_runner(manifest: dict, *, push: bool = True) -> tuple[Path, dict]:
    return kaggle_jobs.run_script_job(JOB_SLUG, JOB_SCRIPT, manifest, OUTPUTS / "tmp" / "score_job", start=push)


def candidates(
    sb: dict,
    duration: float,
    *,
    force: bool = False,
    runner: Runner | None = None,
    out_dir: Path | None = None,
    log_path: Path = RUNS_PATH,
) -> list[Path]:
    """Generate whichever score candidates are missing, all in one GPU job. Returns every candidate that exists."""
    todo = plan(sb, duration, out_dir=out_dir, force=force)
    if todo:
        music = sb["music"]
        manifest = {
            "model": MODEL, "steps": STEPS, "caption": music["caption"], "bpm": music["tempo_bpm"],
            "key": music["key"], "duration": todo[0]["duration"],
            "items": [{"file": item["file"], "seed": item["seed"]} for item in todo],
        }
        folder, job = (runner or kaggle_runner)(manifest)
        report_path = folder / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        by_file = {record["file"]: record for record in report.get("items", [])}
        made = 0
        for item in todo:
            record = by_file.get(item["file"], {})
            source = folder / item["file"]
            ok = record.get("status") == "ok" and source.is_file() and source.stat().st_size > 0
            log_run({
                "stage": "music", "shot": None, "provider": "kaggle", "model": MODEL,
                "params": {"caption": music["caption"], "bpm": music["tempo_bpm"], "key": music["key"],
                           "duration": item["duration"], "steps": STEPS, "instrumental": True},
                "seed": item["seed"], "attempt": 1, "latency_s": record.get("seconds"),
                "gpu_seconds": record.get("seconds"), "gpu": report.get("gpu"), "job": job.get("job"),
                "status": "ok" if ok else "failed",
                "error": None if ok else record.get("error") or f"job steps failed: {report.get('errors')}",
                "output": rel(item["output"]), "cost_usd": 0.0,
            }, path=log_path)
            if ok:
                item["output"].parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, item["output"])
                mark_output(item["output"], item["key"], {"kind": "score_candidate", "seed": item["seed"], "model": MODEL})
                made += 1
        log_run({
            "stage": "music", "shot": None, "provider": "kaggle", "model": "gpu-job",
            "params": {"candidates": len(todo), "steps": report.get("steps"), "setup_seconds": report.get("setup_seconds"),
                       "generate_seconds": report.get("generate_seconds")},
            "seed": None, "attempt": 1, "latency_s": round(job.get("job_minutes", 0) * 60, 1),
            "gpu_seconds": report.get("total_seconds"), "gpu": report.get("gpu"), "job": job.get("job"),
            "status": "ok" if made == len(todo) else "partial" if made else "failed",
            "error": ", ".join(report.get("errors", [])) or None, "output": None, "cost_usd": 0.0,
        }, path=log_path)
        print(f"  music: {made} of {len(todo)} candidates made")
        if not made:
            raise ProviderError(f"the score job produced nothing; see {rel(folder)}")
    else:
        print("  music: all score candidates are cached")
    return [path for seed in CANDIDATE_SEEDS if (path := candidate_path(seed, out_dir)).is_file()]
