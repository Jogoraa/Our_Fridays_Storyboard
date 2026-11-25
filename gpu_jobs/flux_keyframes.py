"""Runs on a Kaggle GPU. Generates reference images and keyframes with FLUX.2 klein 4B (Apache 2.0).

The local keyframes stage replaces the MANIFEST_B64 line with the work to do, pushes this file as
a kernel, and downloads /kaggle/working afterwards. Each image is saved as soon as it is made, so
a session that times out keeps what it finished. report.json records seconds per image.
"""
import base64
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
report = {"model": None, "setup_seconds": None, "items": [], "errors": []}


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

# Kaggle gives two 15 GB GPUs. The text encoder and the image model are each about 8 GB, so on one
# card they have to take turns (slow, and what one leaves behind starves the other). Spread across
# both cards nothing has to move. If that is not possible, fall back to taking turns on one card.
placement = "one GPU, models take turns"
pipe = None
if torch.cuda.device_count() >= 2:
    try:
        pipe = Flux2KleinPipeline.from_pretrained(manifest["model"], torch_dtype=torch.bfloat16, device_map="balanced")
        placement = "two GPUs, one model on each"
    except Exception as exc:
        report["placement_error"] = f"{type(exc).__name__}: {exc}"[:300]
        pipe = None
if pipe is None:
    pipe = Flux2KleinPipeline.from_pretrained(manifest["model"], torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
report["placement"] = placement
report["setup_seconds"] = round(time.time() - started, 1)
report["gpu"] = torch.cuda.get_device_name(0)
save_report()


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


def free_gpu():
    import gc

    if placement.startswith("one GPU"):
        try:
            pipe.maybe_free_model_hooks()  # send every model back to the CPU, whatever state a failure left
        except Exception:
            pass
    gc.collect()
    for index in range(torch.cuda.device_count()):
        with torch.cuda.device(index):
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()


def generate(item, reference_side, scale):
    width = int(item["width"] * scale) // 16 * 16
    height = int(item["height"] * scale) // 16 * 16
    references = [shrink(load_reference(name), reference_side) for name in item.get("references", [])]
    arguments = dict(
        prompt=item["prompt"], width=width, height=height,
        guidance_scale=manifest["guidance_scale"], num_inference_steps=manifest["steps"],
        generator=torch.Generator(device="cpu").manual_seed(item["seed"]),
    )
    if references:
        arguments["image"] = references if len(references) > 1 else references[0]
    return pipe(**arguments).images[0], width, height


# If memory runs out, try again with smaller references, then with a smaller picture.
LADDER = [(manifest.get("reference_max_side", 512), 1.0), (384, 1.0), (384, 0.8334)]

for item in manifest["items"]:
    began = time.time()
    record = {"file": item["file"], "seed": item["seed"], "attempts": []}
    for reference_side, scale in LADDER:
        free_gpu()
        try:
            image, width, height = generate(item, reference_side, scale)
        except Exception as exc:  # keep going: one bad image must not lose the rest
            record["attempts"].append({"reference_side": reference_side, "scale": scale,
                                       "error": f"{type(exc).__name__}: {exc}"[:300]})
            del exc
            continue
        image.save(os.path.join(OUT, item["file"]), quality=95)
        record.update(status="ok", width=width, height=height, reference_side=reference_side,
                      peak_vram_gb=round(max(torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())) / 1e9, 2))
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

save_report()
print("done", json.dumps({k: report[k] for k in ("setup_seconds", "total_seconds", "errors")}))
