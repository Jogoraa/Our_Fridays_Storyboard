"""Runs on a Kaggle GPU. Animates keyframes with Wan 2.2 TI2V-5B (Apache 2.0), image-to-video.

The local video stage replaces the MANIFEST_B64 line, pushes this file as a kernel and downloads
/kaggle/working afterwards. Each clip is saved as soon as it is made. The keyframe already holds
the subject, place and light, so the prompt for each clip is only motion and camera.
"""
import base64
import gc
import io
import json
import os
import subprocess
import sys
import time

MANIFEST_B64 = ""  # filled in by pipeline/video.py

OUT = "/kaggle/working"
os.environ.setdefault("HF_HOME", "/tmp/hf")
started = time.time()
manifest = json.loads(base64.b64decode(MANIFEST_B64).decode("utf-8"))
report = {"model": manifest["model"], "setup_seconds": None, "items": [], "errors": []}


def save_report():
    report["total_seconds"] = round(time.time() - started, 1)
    with open(os.path.join(OUT, "report.json"), "w") as handle:
        json.dump(report, handle, indent=2)


save_report()
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-U",
     "git+https://github.com/huggingface/diffusers.git", "transformers", "accelerate", "ftfy", "imageio", "imageio-ffmpeg"],
    check=False,
)

import torch  # noqa: E402
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline  # noqa: E402
from diffusers.utils import export_to_video  # noqa: E402
from PIL import Image  # noqa: E402

# The first job loaded everything onto one 15 GB card with the models taking turns and ran out of
# memory (FAILURES F16). Kaggle gives two cards: put the text encoder on one and the video model on
# the other. If that is not possible, fall back to taking turns and reset placement before each try.
vae = AutoencoderKLWan.from_pretrained(manifest["model"], subfolder="vae", torch_dtype=torch.float32)
placement = "one GPU, models take turns"
pipe = None
if torch.cuda.device_count() >= 2:
    try:
        pipe = WanImageToVideoPipeline.from_pretrained(manifest["model"], vae=vae, torch_dtype=torch.bfloat16, device_map="balanced")
        placement = "two GPUs, models spread"
    except Exception as exc:
        report["placement_error"] = f"{type(exc).__name__}: {exc}"[:300]
        pipe = None
if pipe is None:
    pipe = WanImageToVideoPipeline.from_pretrained(manifest["model"], vae=vae, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
report["placement"] = placement
for option in ("enable_tiling", "enable_slicing"):
    try:
        getattr(pipe.vae, option)()
    except Exception:
        pass
report["setup_seconds"] = round(time.time() - started, 1)
report["gpu"] = torch.cuda.get_device_name(0)
save_report()


def cover(image, width, height):
    """Scale and centre-crop the keyframe to exactly the clip size."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - width) // 2, (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def generate(item, frames, steps):
    image = cover(Image.open(io.BytesIO(base64.b64decode(item["image_b64"]))).convert("RGB"), item["width"], item["height"])
    output = pipe(
        image=image, prompt=item["prompt"], negative_prompt=manifest["negative_prompt"],
        height=item["height"], width=item["width"], num_frames=frames,
        guidance_scale=manifest["guidance_scale"], num_inference_steps=steps,
        generator=torch.Generator(device="cpu").manual_seed(item["seed"]),
    ).frames[0]
    export_to_video(output, os.path.join(OUT, item["file"]), fps=manifest["fps"])


# If memory runs out or a clip fails, try fewer frames, then fewer steps as well.
LADDER = [(manifest["num_frames"], manifest["steps"]), (49, manifest["steps"]), (33, 20)]
budget_seconds = manifest.get("budget_minutes", 300) * 60

for item in manifest["items"]:
    began = time.time()
    record = {"file": item["file"], "seed": item["seed"], "width": item["width"], "height": item["height"], "attempts": []}
    if time.time() - started > budget_seconds:
        record.update(status="failed", error="time budget for this job was used up before this clip started")
        report["errors"].append(item["file"])
        report["items"].append(record)
        save_report()
        continue
    for frames, steps in LADDER:
        if placement.startswith("one GPU"):
            try:
                pipe.maybe_free_model_hooks()
            except Exception:
                pass
        gc.collect()
        for index in range(torch.cuda.device_count()):
            with torch.cuda.device(index):
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
        try:
            generate(item, frames, steps)
        except Exception as exc:
            record["attempts"].append({"frames": frames, "steps": steps, "error": f"{type(exc).__name__}: {exc}"[:300]})
            del exc
            continue
        record.update(status="ok", frames=frames, steps=steps,
                      peak_vram_gb=round(max(torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())) / 1e9, 2))
        break
    else:
        record["status"] = "failed"
        record["error"] = record["attempts"][-1]["error"]
        report["errors"].append(item["file"])
    record["seconds"] = round(time.time() - began, 1)
    report["items"].append(record)
    print(json.dumps(record), flush=True)
    save_report()

save_report()
print("done", json.dumps({k: report[k] for k in ("setup_seconds", "total_seconds", "errors")}))
