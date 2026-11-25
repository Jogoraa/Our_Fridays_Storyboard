"""Run a script on a free Kaggle GPU and bring its output files back.

Kaggle has no "run this now" API for our own machine; a job is a notebook kernel pushed with the
Kaggle CLI, polled until it finishes, and its /kaggle/working folder downloaded.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from pipeline.common import ConfigError, ProviderError, RetryableError, require_env

CLI = ["uvx", "--with", "six", "kaggle@latest"]
POLL_SECONDS = 30
FINISHED = ("complete",)
FAILED = ("error", "cancel")


def _env() -> dict[str, str]:
    """Kaggle accepts either the new single token or the older username + key pair."""
    env = dict(os.environ)
    env["KAGGLE_USERNAME"] = require_env("KAGGLE_USERNAME")
    try:
        env["KAGGLE_API_TOKEN"] = require_env("KAGGLE_API_TOKEN")
    except ConfigError:
        env["KAGGLE_KEY"] = require_env("KAGGLE_KEY")
    return env


def _cli(args: list[str], *, check: bool = True) -> str:
    if not shutil.which("uvx"):
        raise ConfigError("uvx was not found on PATH (it ships with uv)")
    result = subprocess.run(CLI + args, env=_env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (result.stdout + result.stderr).strip()
    if check and result.returncode != 0:
        raise RetryableError(f"kaggle {' '.join(args[:2])} failed: {output[-400:]}")
    return output


def kernel_ref(slug: str) -> str:
    return f"{require_env('KAGGLE_USERNAME')}/{slug}"


def push(slug: str, script: Path, *, gpu: bool = True, internet: bool = True, datasets: list[str] | None = None) -> str:
    """Upload the script as a kernel and start it. Returns the kernel reference."""
    ref = kernel_ref(slug)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        shutil.copy(script, folder / "job.py")
        metadata = {
            "id": ref, "title": slug, "code_file": "job.py", "language": "python", "kernel_type": "script",
            "is_private": True, "enable_gpu": gpu, "enable_internet": internet,
            "dataset_sources": datasets or [], "competition_sources": [], "kernel_sources": [], "model_sources": [],
        }
        (folder / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        output = _cli(["kernels", "push", "-p", str(folder)])
    if "error" in output.lower() and "successfully" not in output.lower():
        raise ProviderError(f"kaggle push refused: {output[-400:]}")
    return ref


def status(ref: str) -> str:
    """One of: queued, running, complete, error, cancel (lower case)."""
    output = _cli(["kernels", "status", ref]).lower()
    for word in ("complete", "error", "cancel", "running", "queued"):
        if word in output:
            return word
    return output[-80:]


def wait(ref: str, *, timeout_minutes: float = 120, sleep=time.sleep) -> float:
    """Block until the kernel finishes. Returns the minutes it took. Raises if it failed or timed out."""
    started = time.monotonic()
    while True:
        state = status(ref)
        minutes = (time.monotonic() - started) / 60
        if state in FINISHED:
            return minutes
        if state in FAILED:
            raise ProviderError(f"kaggle job {ref} ended with status '{state}'")
        if minutes > timeout_minutes:
            raise ProviderError(f"kaggle job {ref} still '{state}' after {timeout_minutes:g} minutes")
        sleep(POLL_SECONDS)


def download(ref: str, into: Path) -> list[Path]:
    """Fetch everything the kernel wrote to /kaggle/working, plus its log."""
    into.mkdir(parents=True, exist_ok=True)
    _cli(["kernels", "output", ref, "-p", str(into)])
    return sorted(p for p in into.rglob("*") if p.is_file())
