"""Keyframes stage: a reference image per character first, then one keyframe per shot per aspect ratio.

Every keyframe is conditioned on the references of the characters in it, and every prompt ends with
the same style block, so the two people and the look stay the same from shot to shot.

Images are made by FLUX.2 klein 4B on a Kaggle GPU. All missing images go into ONE job, because a
job waits in a queue for about fifteen minutes however small it is.
"""
from __future__ import annotations

import base64
import json
import shutil
from collections.abc import Callable
from pathlib import Path

from pipeline import kaggle_jobs
from pipeline.common import OUTPUTS, ROOT, RUNS_PATH, ProviderError, cache_key, is_cached, log_run, mark_output, rel
from pipeline.shots import aspect_tag, keyframe_path

STAGE = "keyframes"
VERSION = "1"
MODEL = "black-forest-labs/FLUX.2-klein-4B"
STEPS = 4
GUIDANCE = 1.0
CANDIDATES = 3                               # reference options per character; one is chosen by eye
SIZES = {"9:16": (864, 1536), "16:9": (1536, 864)}   # multiples of 16; upscaled to 1080p in the edit
REFERENCE_SIZE = (864, 1152)
JOB_SCRIPT = ROOT / "gpu_jobs" / "flux_keyframes.py"
JOB_SLUG = "our-fridays-keyframes"

Runner = Callable[[dict], tuple[Path, dict]]


def reference_candidates(character: dict, root: Path | None = None) -> list[Path]:
    folder = root or OUTPUTS / "references"
    return [folder / f"{character['id']}_c{n}.jpg" for n in range(1, CANDIDATES + 1)]


def chosen_reference(character: dict, root: Path | None = None) -> Path:
    """The approved reference for a character: the storyboard names it, else candidate 1."""
    if character.get("reference_asset"):
        name = Path(character["reference_asset"]).name
        return (root or OUTPUTS / "references") / name
    return reference_candidates(character, root)[0]


def reference_prompt(character: dict, style_block: str) -> str:
    return (
        f"Character reference portrait of {character['name']}: {character['description']} "
        f"Wearing: {character['wardrobe']} Waist-up, facing the camera, relaxed neutral expression, "
        f"plain softly lit warm grey background, even light on the face. {style_block}"
    )


def keyframe_prompt(shot: dict, characters: dict[str, dict], style_block: str, aspect: str) -> str:
    cast = [characters[c] for c in shot["characters"]]
    who = " ".join(
        f"{c['name']} is the {c.get('noun', 'person')} from reference image {i + 1}: "
        f"same face, same hair, {c['wardrobe']}"
        for i, c in enumerate(cast)
    )
    framing = "Vertical frame, subject centred." if aspect == "9:16" else "Wide horizontal frame, subject centred."
    # A shot may carry its own look (for example an imagined scene); otherwise the film's style block applies.
    return " ".join(part for part in (shot["keyframe_prompt"], who, framing, shot.get("style_block", style_block)) if part)


def _reference_key(character: dict, style_block: str, seed: int) -> str:
    return cache_key(STAGE, VERSION, {
        "kind": "reference", "model": MODEL, "steps": STEPS, "guidance": GUIDANCE,
        "prompt": reference_prompt(character, style_block), "seed": seed, "size": REFERENCE_SIZE,
    })


def plan(sb: dict, *, references: Path | None = None, keyframes: Path | None = None,
         only_shot: str | None = None, force: bool = False) -> list[dict]:
    """Everything that is missing or out of date, in the order it must be made."""
    style = sb["style_block"]
    characters = {c["id"]: c for c in sb["characters"]}
    todo: list[dict] = []
    reference_keys: dict[str, str] = {}

    for index, character in enumerate(sb["characters"]):
        for n, output in enumerate(reference_candidates(character, references), start=1):
            seed = 7000 + 100 * index + n
            key = _reference_key(character, style, seed)
            if output == chosen_reference(character, references):
                reference_keys[character["id"]] = key
            if (force and not only_shot) or not is_cached(output, key):
                todo.append({
                    "kind": "reference", "file": output.name, "output": output, "key": key,
                    "prompt": reference_prompt(character, style), "seed": seed,
                    "width": REFERENCE_SIZE[0], "height": REFERENCE_SIZE[1], "references": [],
                    "shot": None, "aspect": None,
                })

    for shot in sb["shots"]:
        if only_shot and shot["id"] != only_shot:
            continue
        cast = [characters[c] for c in shot["characters"]]
        for aspect, (width, height) in SIZES.items():
            prompt = keyframe_prompt(shot, characters, style, aspect)
            # The key uses each reference's own key, not its file hash, so a keyframe planned in the
            # same job as its reference does not look out of date once the reference file arrives.
            key = cache_key(STAGE, VERSION, {
                "kind": "keyframe", "model": MODEL, "steps": STEPS, "guidance": GUIDANCE, "prompt": prompt,
                "seed": shot["seed"], "size": [width, height],
                "references": [reference_keys[c["id"]] for c in cast],
            })
            output = keyframe_path(shot["id"], aspect, keyframes)
            if force or not is_cached(output, key):
                todo.append({
                    "kind": "keyframe", "file": output.name, "output": output, "key": key, "prompt": prompt,
                    "seed": shot["seed"], "width": width, "height": height,
                    "references": [chosen_reference(c, references).name for c in cast],
                    "shot": shot["id"], "aspect": aspect,
                })
    return todo


def build_manifest(todo: list[dict], references: Path | None = None) -> dict:
    """What the GPU job needs. References not made in this job are sent along inside the manifest."""
    made_here = {item["file"] for item in todo if item["kind"] == "reference"}
    embedded: dict[str, str] = {}
    folder = references or OUTPUTS / "references"
    for item in todo:
        for name in item["references"]:
            if name not in made_here and name not in embedded:
                path = folder / name
                if not path.is_file():
                    raise ProviderError(f"reference {name} does not exist and is not planned in this job")
                embedded[name] = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "model": MODEL, "steps": STEPS, "guidance_scale": GUIDANCE, "embedded": embedded,
        "items": [{k: item[k] for k in ("file", "prompt", "seed", "width", "height", "references")} for item in todo],
    }


def kaggle_runner(manifest: dict, *, push: bool = True) -> tuple[Path, dict]:
    """Push one Kaggle job with the manifest baked into the script, wait, and download its output.

    With push=False nothing is started: the job already pushed is waited for and collected. That is
    how a run resumes after this machine sleeps or the terminal closes while the GPU is still busy.
    """
    work = OUTPUTS / "tmp" / "keyframes_job"
    if not push:
        ref = kaggle_jobs.kernel_ref(JOB_SLUG)
        print(f"  keyframes: collecting the job already on Kaggle ({JOB_SLUG})")
        minutes = kaggle_jobs.wait(ref, timeout_minutes=150)
        downloaded = work / "output"
        shutil.rmtree(downloaded, ignore_errors=True)
        kaggle_jobs.download(ref, downloaded)
        return downloaded, {"job_minutes": round(minutes, 2), "job": JOB_SLUG, "collected": True}
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    encoded = base64.b64encode(json.dumps(manifest, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = work / "job.py"
    script.write_text(
        JOB_SCRIPT.read_text(encoding="utf-8").replace('MANIFEST_B64 = ""', f'MANIFEST_B64 = "{encoded}"', 1),
        encoding="utf-8",
    )
    ref = kaggle_jobs.push(JOB_SLUG, script)
    print(f"  keyframes: pushed {len(manifest['items'])} images to Kaggle as {JOB_SLUG}; waiting for the GPU")
    minutes = kaggle_jobs.wait(ref, timeout_minutes=150)
    downloaded = work / "output"
    kaggle_jobs.download(ref, downloaded)
    return downloaded, {"job_minutes": round(minutes, 2), "job": JOB_SLUG}


def run(
    sb: dict,
    *,
    only_shot: str | None = None,
    force: bool = False,
    runner: Runner | None = None,
    references: Path | None = None,
    keyframes: Path | None = None,
    log_path: Path = RUNS_PATH,
) -> list[dict]:
    """Generate whatever is missing. Returns the items that were made (empty when everything is cached)."""
    todo = plan(sb, references=references, keyframes=keyframes, only_shot=only_shot, force=force)
    if not todo:
        print("  keyframes: all references and keyframes are cached")
        return []
    runner = runner or kaggle_runner
    folder, job = runner(build_manifest(todo, references))
    report_path = folder / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {"items": []}
    by_file = {record["file"]: record for record in report.get("items", [])}

    made, failed = [], []
    for item in todo:
        record = by_file.get(item["file"], {})
        source = folder / item["file"]
        ok = record.get("status") == "ok" and source.is_file() and source.stat().st_size > 0
        log_run({
            "stage": STAGE, "shot": item["shot"], "provider": "kaggle", "model": MODEL,
            "params": {"kind": item["kind"], "aspect": item["aspect"], "prompt": item["prompt"],
                       "width": item["width"], "height": item["height"], "steps": STEPS,
                       "guidance_scale": GUIDANCE, "references": item["references"]},
            "seed": item["seed"], "attempt": 1, "latency_s": record.get("seconds"),
            "gpu_seconds": record.get("seconds"), "gpu": report.get("gpu"), "job": job.get("job"),
            "status": "ok" if ok else "failed", "error": None if ok else record.get("error", "no image came back"),
            "output": rel(item["output"]), "cost_usd": 0.0,
        }, path=log_path)
        if not ok:
            failed.append(item["file"])
            continue
        item["output"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, item["output"])
        mark_output(item["output"], item["key"], {
            "kind": item["kind"], "shot": item["shot"], "aspect": item["aspect"], "seed": item["seed"],
            "model": MODEL, "gpu_seconds": record.get("seconds"),
        })
        made.append(item)
    log_run({
        "stage": STAGE, "shot": None, "provider": "kaggle", "model": "gpu-job",
        "params": {"images": len(todo), "setup_seconds": report.get("setup_seconds"),
                   "run_seconds": report.get("total_seconds")},
        "seed": None, "attempt": 1, "latency_s": round(job.get("job_minutes", 0) * 60, 1),
        "gpu_seconds": report.get("total_seconds"), "gpu": report.get("gpu"), "job": job.get("job"),
        "status": "ok" if not failed else "partial", "error": ", ".join(failed) or None, "output": None, "cost_usd": 0.0,
    }, path=log_path)
    print(f"  keyframes: {len(made)} made, {len(failed)} failed" + (f" ({', '.join(failed)})" if failed else ""))
    if failed and not made:
        raise ProviderError(f"the keyframe job produced nothing; see {rel(folder)}")
    return made
