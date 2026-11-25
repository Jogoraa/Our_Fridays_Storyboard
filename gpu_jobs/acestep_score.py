"""Runs on a Kaggle GPU. Generates score candidates with ACE-Step 1.5 (MIT licence).

The local music stage replaces the MANIFEST_B64 line, pushes this file as a kernel and downloads
/kaggle/working afterwards. ACE-Step needs its own Python environment, so this script clones the
project, lets uv build that environment, and runs the generation inside it.
"""
import base64
import json
import os
import subprocess
import sys
import time

MANIFEST_B64 = ""  # filled in by pipeline/music.py

OUT = "/kaggle/working"
REPO = "/tmp/ACE-Step-1.5"
started = time.time()
manifest = json.loads(base64.b64decode(MANIFEST_B64).decode("utf-8"))
report = {"model": manifest["model"], "steps": [], "items": [], "errors": []}


def save_report():
    report["total_seconds"] = round(time.time() - started, 1)
    with open(os.path.join(OUT, "report.json"), "w") as handle:
        json.dump(report, handle, indent=2)


def step(name, command, cwd=None, env=None):
    began = time.time()
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    record = {"step": name, "seconds": round(time.time() - began, 1), "returncode": result.returncode}
    if result.returncode != 0:
        record["tail"] = (result.stdout + result.stderr)[-1500:]
        report["errors"].append(name)
    report["steps"].append(record)
    print(json.dumps(record), flush=True)
    save_report()
    return result


INNER = r'''
import json, os, shutil, sys, time
manifest = json.load(open(sys.argv[1]))
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music

began = time.time()
dit = AceStepHandler()
dit.initialize_service(project_root=os.getcwd(), config_path=manifest["model"], device="cuda")
llm = LLMHandler()  # not initialised: the caption, tempo and key are given, so no language-model planning
setup = round(time.time() - began, 1)

params = GenerationParams(
    caption=manifest["caption"], lyrics="[Instrumental]", instrumental=True,
    bpm=manifest["bpm"], keyscale=manifest["key"], duration=manifest["duration"],
    inference_steps=manifest["steps"], thinking=False,
    use_cot_metas=False, use_cot_caption=False, use_cot_language=False,
)
seeds = [item["seed"] for item in manifest["items"]]
config = GenerationConfig(batch_size=len(seeds), use_random_seed=False, seeds=seeds, audio_format="flac")
began = time.time()
result = generate_music(dit, llm, params, config, save_dir="/tmp/score_out")
seconds = round(time.time() - began, 1)
items = []
if result.success:
    for item, audio in zip(manifest["items"], result.audios):
        shutil.copyfile(audio["path"], os.path.join("/kaggle/working", item["file"]))
        items.append({"file": item["file"], "seed": audio["params"].get("seed", item["seed"]), "status": "ok",
                      "seconds": round(seconds / len(seeds), 1)})
else:
    items = [{"file": item["file"], "seed": item["seed"], "status": "failed", "error": str(result.error)[:500]}
             for item in manifest["items"]]
json.dump({"setup_seconds": setup, "generate_seconds": seconds, "items": items},
          open("/kaggle/working/inner_report.json", "w"), indent=2)
print("inner done", setup, seconds, len(items))
'''

save_report()
step("install uv", [sys.executable, "-m", "pip", "install", "-q", "uv"])
step("clone", ["git", "clone", "--depth", "1", "https://github.com/ACE-Step/ACE-Step-1.5.git", REPO])
step("uv sync", ["uv", "sync"], cwd=REPO)
step("download model", ["uv", "run", "acestep-download"], cwd=REPO)
with open(os.path.join(REPO, "score_manifest.json"), "w") as handle:
    json.dump(manifest, handle)
with open(os.path.join(REPO, "score_inner.py"), "w") as handle:
    handle.write(INNER)
step("generate", ["uv", "run", "python", "score_inner.py", "score_manifest.json"], cwd=REPO)

inner = os.path.join(OUT, "inner_report.json")
if os.path.exists(inner):
    report.update(json.load(open(inner)))
try:
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
    report["gpu"] = gpu.stdout.strip().splitlines()[0]
except Exception:
    report["gpu"] = None
save_report()
print("done", json.dumps({"errors": report["errors"], "total_seconds": report["total_seconds"]}))
