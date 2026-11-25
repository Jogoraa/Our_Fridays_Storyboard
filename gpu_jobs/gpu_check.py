"""Runs on Kaggle. Reports which GPU, how much memory and disk the free tier actually gives us."""
import json
import shutil
import subprocess
import time

started = time.time()
report = {"gpus": [], "torch": None, "cuda": False}
try:
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=60,
    )
    report["gpus"] = [line.strip() for line in query.stdout.splitlines() if line.strip()]
    report["nvidia_smi_error"] = query.stderr.strip()[:300] or None
except Exception as exc:  # no driver means no GPU was attached
    report["nvidia_smi_error"] = str(exc)[:300]
try:
    import torch

    report["torch"] = torch.__version__
    report["cuda"] = torch.cuda.is_available()
except Exception as exc:
    report["torch_error"] = str(exc)[:300]
try:
    import urllib.request

    urllib.request.urlopen("https://huggingface.co", timeout=20)
    report["internet"] = True
except Exception as exc:
    report["internet"] = f"no: {exc}"[:200]
total, used, free = shutil.disk_usage("/kaggle/working")
report["disk_free_gb"] = round(free / 1e9, 1)
report["seconds"] = round(time.time() - started, 1)
print(json.dumps(report, indent=2))
with open("/kaggle/working/gpu_check.json", "w") as handle:
    json.dump(report, handle, indent=2)
