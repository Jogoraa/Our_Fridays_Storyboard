"""Runs on a Kaggle GPU. Generates reference images and keyframes with FLUX.2 klein 4B (Apache 2.0).

The local keyframes stage replaces the MANIFEST_B64 line with the work to do, pushes this file as
a kernel, and downloads /kaggle/working afterwards. Each image is saved as soon as it is made, so
a session that times out keeps what it finished. report.json records every attempt.

Memory decides how this job is shaped (FAILURES.md F14). Two ways of loading the model were each
found to work for one kind of image on two 15 GB T4s, so the job uses each for what it can do:

  - images conditioned on a reference: text encoder on one GPU, image model on the other;
  - images from text alone: both models taking turns on one GPU.
"""
import base64
import gc
import io
import json
import os
import subprocess
import sys
import time

MANIFEST_B64 = ""  # filled in by pipeline/keyframes.py

OUT = "/kaggle/working"
os.environ.setdefault("HF_HOME", "/tmp/hf")
started = time.time()
report = {"model": None, "setup_seconds": None, "items": [], "errors": [], "phases": []}


def save_report():
    report["total_seconds"] = round(time.time() - started, 1)
    with open(os.path.join(OUT, "report.json"), "w") as handle:
        json.dump(report, handle, indent=2)


manifest = json.loads(base64.b64decode(MANIFEST_B64).decode("utf-8"))
report["model"] = manifest["model"]
save_report()

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-U",
     "git+https://github.com/huggingface/diffusers.git", "transformers", "accelerate", "sentencepiece"],
    check=False,
)

import torch  # noqa: E402
from diffusers import Flux2KleinPipeline  # noqa: E402
from PIL import Image  # noqa: E402

report["gpu"] = torch.cuda.get_device_name(0)
report["gpu_count"] = torch.cuda.device_count()
pipe = None
placement = None


def free_gpu():
    if pipe is not None and placement == "one GPU, models take turns":
        try:
            pipe.maybe_free_model_hooks()  # send every model back to the CPU, whatever state a failure left
        except Exception:
            pass
    gc.collect()
    for index in range(torch.cuda.device_count()):
        with torch.cuda.device(index):
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()


def load(two_gpus):
    """Load the model one of two ways. Returns the pipeline and a plain description of the placement."""
    began = time.time()
    if two_gpus and torch.cuda.device_count() >= 2:
        try:
            loaded = Flux2KleinPipeline.from_pretrained(manifest["model"], torch_dtype=torch.bfloat16, device_map="balanced")
            report["phases"].append({"placement": "two GPUs, one model on each", "load_seconds": round(time.time() - began, 1)})
            return loaded, "two GPUs, one model on each"
        except Exception as exc:
            report["placement_error"] = f"{type(exc).__name__}: {exc}"[:300]
    loaded = Flux2KleinPipeline.from_pretrained(manifest["model"], torch_dtype=torch.bfloat16)
    loaded.enable_model_cpu_offload()
    report["phases"].append({"placement": "one GPU, models take turns", "load_seconds": round(time.time() - began, 1)})
    return loaded, "one GPU, models take turns"


def load_reference(name):
    """A reference is either an image made earlier in this job or one sent along in the manifest."""
    local = os.path.join(OUT, name)
    if os.path.exists(local):
        return Image.open(local).convert("RGB")
    if name in manifest.get("embedded", {}):
        return Image.open(io.BytesIO(base64.b64decode(manifest["embedded"][name]))).convert("RGB")
    raise FileNotFoundError(f"reference {name} is neither generated in this job nor embedded")


def shrink(image, longest):
    """Reference images are conditioning, not output. Every reference pixel becomes tokens the model
    must attend to, and attention memory grows with the square of the token count."""
    scale = longest / max(image.size)
    if scale >= 1:
        return image
    size = (max(16, int(image.width * scale) // 16 * 16), max(16, int(image.height * scale) // 16 * 16))
    return image.resize(size, Image.LANCZOS)


def generate(item, reference_side, scale):
    width = int(item["width"] * scale) // 16 * 16
    height = int(item["height"] * scale) // 16 * 16
    references = [shrink(load_reference(name), reference_side) for name in item.get("references", [])]
    if len(references) > 1:
        # Two separate references did not fit in memory; one image with both people side by side does.
        height_px = min(image.height for image in references)
        scaled = [image.resize((int(image.width * height_px / image.height) // 16 * 16, height_px // 16 * 16), Image.LANCZOS)
                  for image in references]
        sheet = Image.new("RGB", (sum(image.width for image in scaled), scaled[0].height))
        offset = 0
        for image in scaled:
            sheet.paste(image, (offset, 0))
            offset += image.width
        references = [sheet]
    arguments = dict(
        prompt=item["prompt"], width=width, height=height,
        guidance_scale=manifest["guidance_scale"], num_inference_steps=manifest["steps"],
        generator=torch.Generator(device="cpu").manual_seed(item["seed"]),
    )
    if references:
        arguments["image"] = references if len(references) > 1 else references[0]
    return pipe(**arguments).images[0], width, height


def run_items(items, ladder):
    for item in items:
        began = time.time()
        record = {"file": item["file"], "seed": item["seed"], "placement": placement, "attempts": []}
        for reference_side, scale in ladder:
            free_gpu()
            try:
                image, width, height = generate(item, reference_side, scale)
            except Exception as exc:  # keep going: one bad image must not lose the rest
                record["attempts"].append({"reference_side": reference_side, "scale": scale,
                                           "error": f"{type(exc).__name__}: {exc}"[:300]})
                del exc
                continue
            image.save(os.path.join(OUT, item["file"]), quality=95)
            record.update(
                status="ok", width=width, height=height, reference_side=reference_side,
                peak_vram_gb=round(max(torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())) / 1e9, 2),
            )
            del image
            break
        else:
            record["status"] = "failed"
            record["error"] = record["attempts"][-1]["error"]
            report["errors"].append(item["file"])
        record["seconds"] = round(time.time() - began, 2)
        report["items"].append(record)
        print(json.dumps(record), flush=True)
        save_report()


conditioned = [item for item in manifest["items"] if item.get("references")]
from_text = [item for item in manifest["items"] if not item.get("references")]
# Each ladder starts at the size measured to fit and steps down if memory still runs out.
ladders = manifest.get("ladders", {})

if from_text:
    pipe, placement = load(two_gpus=False)
    if report["setup_seconds"] is None:
        report["setup_seconds"] = round(time.time() - started, 1)
    run_items(from_text, ladders.get("from_text", [[512, 1.0], [512, 0.8334], [512, 0.75]]))
    free_gpu()
    del pipe
    pipe = None
    gc.collect()
    torch.cuda.empty_cache()

if conditioned:
    pipe, placement = load(two_gpus=True)
    if report["setup_seconds"] is None:
        report["setup_seconds"] = round(time.time() - started, 1)
    run_items(conditioned, ladders.get("conditioned", [[384, 0.8334], [320, 0.8334], [320, 0.75]]))

save_report()
print("done", json.dumps({k: report[k] for k in ("setup_seconds", "total_seconds", "errors")}))
