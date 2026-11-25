"""Video stage: animate chosen keyframes with Wan 2.2 TI2V-5B on a Kaggle GPU.

Only shots whose storyboard entry says render "video" for an aspect ratio are sent. Everything else
stays a moving still, and so does any shot whose clip fails: the shots stage falls back by itself.
GPU time is the scarce thing, so clips are drafted small and short and all go into one job.
"""
from __future__ import annotations

import base64
import json
import shutil
from collections.abc import Callable
from pathlib import Path

from pipeline import kaggle_jobs
from pipeline.common import small_jpeg, OUTPUTS, ROOT, RUNS_PATH, cache_key, is_cached, log_run, mark_output, rel
from pipeline.shots import keyframe_path, video_source_path

STAGE = "video"
VERSION = "1"
MODEL = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
SIZES = {"9:16": (480, 832), "16:9": (832, 480)}  # draft size; multiples of 32; upscaled in the edit
NUM_FRAMES = 73          # 3 seconds at 24 fps (the model wants 4k+1 frames)
FPS = 24
STEPS = 30
GUIDANCE = 5.0
NEGATIVE = (
    "overexposed, static frame, blurry details, subtitles, text, watermark, worst quality, low quality, "
    "jpeg artifacts, deformed, extra fingers, malformed hands, distorted face, morphing, flicker, fast motion"
)
JOB_SCRIPT = ROOT / "gpu_jobs" / "wan_i2v.py"
JOB_SLUG = "our-fridays-video"

Runner = Callable[[dict], tuple[Path, dict]]


def plan(sb: dict, *, keyframes: Path | None = None, videos: Path | None = None,
         only_shot: str | None = None, force: bool = False) -> list[dict]:
    todo = []
    for shot in sb["shots"]:
        if only_shot and shot["id"] != only_shot:
            continue
        for aspect, (width, height) in SIZES.items():
            if shot["render"][aspect] != "video":
                continue
            keyframe = keyframe_path(shot["id"], aspect, keyframes)
            if not keyframe.is_file():
                print(f"  video {shot['id']} [{aspect}]: no keyframe yet, skipped")
                continue
            key = cache_key(STAGE, VERSION, {
                "model": MODEL, "prompt": shot["motion_prompt"], "negative": NEGATIVE, "seed": shot["seed"],
                "size": [width, height], "frames": NUM_FRAMES, "steps": STEPS, "guidance": GUIDANCE,
            }, [keyframe])
            output = video_source_path(shot["id"], aspect, videos)
            if force or not is_cached(output, key):
                todo.append({"shot": shot["id"], "aspect": aspect, "file": output.name, "output": output, "key": key,
                             "prompt": shot["motion_prompt"], "seed": shot["seed"], "width": width, "height": height,
                             "keyframe": keyframe})
    return todo


def kaggle_runner(manifest: dict, *, push: bool = True) -> tuple[Path, dict]:
    return kaggle_jobs.run_script_job(JOB_SLUG, JOB_SCRIPT, manifest, OUTPUTS / "tmp" / "video_job",
                                      start=push, timeout_minutes=400)


def run(sb: dict, *, only_shot: str | None = None, force: bool = False, runner: Runner | None = None,
        keyframes: Path | None = None, videos: Path | None = None, log_path: Path = RUNS_PATH) -> list[dict]:
    todo = plan(sb, keyframes=keyframes, videos=videos, only_shot=only_shot, force=force)
    if not todo:
        print("  video: nothing to generate (no shot asks for video, or every clip is cached)")
        return []
    manifest = {
        "model": MODEL, "num_frames": NUM_FRAMES, "fps": FPS, "steps": STEPS, "guidance_scale": GUIDANCE,
        "negative_prompt": NEGATIVE, "budget_minutes": 300,
        "items": [{"file": item["file"], "prompt": item["prompt"], "seed": item["seed"], "width": item["width"],
                   "height": item["height"], "image_b64": base64.b64encode(small_jpeg(item["keyframe"], max(item["width"], item["height"]))).decode("ascii")}
                  for item in todo],
    }
    folder, job = (runner or kaggle_runner)(manifest)
    report_path = folder / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    by_file = {record["file"]: record for record in report.get("items", [])}
    made = []
    for item in todo:
        record = by_file.get(item["file"], {})
        source = folder / item["file"]
        ok = record.get("status") == "ok" and source.is_file() and source.stat().st_size > 0
        log_run({
            "stage": STAGE, "shot": item["shot"], "provider": "kaggle", "model": MODEL,
            "params": {"aspect": item["aspect"], "prompt": item["prompt"], "width": item["width"], "height": item["height"],
                       "frames": record.get("frames", NUM_FRAMES), "steps": record.get("steps", STEPS),
                       "guidance_scale": GUIDANCE, "failed_attempts": len(record.get("attempts", [])),
                       "peak_vram_gb": record.get("peak_vram_gb")},
            "seed": item["seed"], "attempt": 1, "latency_s": record.get("seconds"), "gpu_seconds": record.get("seconds"),
            "gpu": report.get("gpu"), "job": job.get("job"), "status": "ok" if ok else "failed",
            "error": None if ok else record.get("error", "no clip came back"), "output": rel(item["output"]), "cost_usd": 0.0,
        }, path=log_path)
        if ok:
            item["output"].parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, item["output"])
            mark_output(item["output"], item["key"], {"shot": item["shot"], "aspect": item["aspect"], "seed": item["seed"],
                                                       "model": MODEL, "gpu_seconds": record.get("seconds")})
            made.append(item)
    log_run({
        "stage": STAGE, "shot": None, "provider": "kaggle", "model": "gpu-job",
        "params": {"clips": len(todo), "setup_seconds": report.get("setup_seconds")},
        "seed": None, "attempt": 1, "latency_s": round(job.get("job_minutes", 0) * 60, 1),
        "gpu_seconds": report.get("total_seconds"), "gpu": report.get("gpu"), "job": job.get("job"),
        "status": "ok" if len(made) == len(todo) else "partial" if made else "failed",
        "error": ", ".join(report.get("errors", [])) or None, "output": None, "cost_usd": 0.0,
    }, path=log_path)
    print(f"  video: {len(made)} of {len(todo)} clips made; the rest stay moving stills")
    return made
