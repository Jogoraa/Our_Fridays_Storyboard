"""Shared core for every stage: paths, secrets, caching, the run log, retries and FFmpeg helpers."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
RUNS_PATH = ROOT / "runs.jsonl"

T = TypeVar("T")

_env_loaded = False
_SECRET_WORDS = ("key", "token", "secret", "password", "authorization")


class ConfigError(Exception):
    """The machine is not set up to run this stage (missing key, missing FFmpeg)."""


class RetryableError(Exception):
    """A provider failure worth trying again: rate limit, server error, timeout, empty output."""


class ProviderError(Exception):
    """A provider failure that retrying will not fix, or retries ran out."""


# --- secrets -----------------------------------------------------------------

def require_env(name: str) -> str:
    """Return a secret from .env or the environment. Never log the value."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv(ROOT / ".env")
        _env_loaded = True
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing {name} in .env (see .env.example)")
    return value


def has_env(name: str) -> bool:
    try:
        require_env(name)
    except ConfigError:
        return False
    return True


# --- caching -----------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(stage: str, version: str, payload: dict, input_files: Sequence[Path] = ()) -> str:
    """Hash everything that decides an output. Same key means the output is still valid."""
    material = {
        "stage": stage,
        "version": version,
        "payload": payload,
        "inputs": [sha256_file(Path(p)) for p in input_files],
    }
    canonical = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def meta_path(output: Path) -> Path:
    return output.with_name(output.name + ".meta.json")


def is_cached(output: Path, key: str) -> bool:
    """True only if the file exists, is not empty and was written for exactly this key."""
    meta = meta_path(output)
    if not output.is_file() or output.stat().st_size == 0 or not meta.is_file():
        return False
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("key") == key
    except json.JSONDecodeError:
        return False


def mark_output(output: Path, key: str, meta: dict) -> None:
    """Record the key for a file that already exists. Written last, so a crash leaves no false hit."""
    record = {"key": key, "written": _now(), **meta}
    meta_path(output).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_output(output: Path, data: bytes, key: str, meta: dict) -> None:
    """Write via a temp file and rename, then the meta. An interrupted run is never mistaken for a hit."""
    output.parent.mkdir(parents=True, exist_ok=True)
    stale = meta_path(output)
    if stale.exists():
        stale.unlink()
    temp = output.with_name(output.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(output)
    mark_output(output, key, meta)


# --- run log -----------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "***" if any(word in str(k).lower() for word in _SECRET_WORDS) else _mask(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


def log_run(record: dict, path: Path = RUNS_PATH) -> None:
    """Append one line to runs.jsonl. One line per model call attempt."""
    line = {"ts": _now(), **_mask(record)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


# --- retries -----------------------------------------------------------------

def call_with_retry(
    fn: Callable[[], T],
    *,
    stage: str,
    provider: str,
    model: str,
    params: dict,
    shot: str | None = None,
    seed: int | None = None,
    attempts: int = 3,
    base_delay: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    log_path: Path = RUNS_PATH,
    extra: dict | None = None,
) -> T:
    """Call a provider, log every attempt, back off and retry only on RetryableError."""
    base = {"stage": stage, "shot": shot, "provider": provider, "model": model, "params": params, "seed": seed}
    if extra:
        base.update(extra)
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = fn()
        except RetryableError as exc:
            latency = round(time.perf_counter() - started, 3)
            last = attempt == attempts
            log_run(
                {**base, "attempt": attempt, "latency_s": latency,
                 "status": "failed" if last else "retry", "error": str(exc)},
                path=log_path,
            )
            if last:
                raise ProviderError(f"{provider} {model} failed after {attempts} attempts: {exc}") from exc
            sleep(base_delay * 2 ** (attempt - 1))
        except Exception as exc:
            latency = round(time.perf_counter() - started, 3)
            log_run(
                {**base, "attempt": attempt, "latency_s": latency, "status": "failed", "error": str(exc)},
                path=log_path,
            )
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"{provider} {model}: {exc}") from exc
        else:
            latency = round(time.perf_counter() - started, 3)
            log_run(
                {**base, "attempt": attempt, "latency_s": latency, "status": "ok", "error": None},
                path=log_path,
            )
            return result
    raise AssertionError("unreachable")


# --- FFmpeg ------------------------------------------------------------------

def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ConfigError(f"{name} was not found on PATH. Install FFmpeg and try again.")
    return path


def run_ffmpeg(args: list[str], *, capture: bool = False, cwd: Path | None = None) -> str:
    """Run FFmpeg quietly. Returns stderr (where FFmpeg reports measurements) when capture is set."""
    command = [_tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", *args]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-12:])
        raise ProviderError(f"ffmpeg failed:\n{tail}")
    return result.stderr if capture else ""


def probe_duration(path: Path) -> float:
    command = [
        _tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not result.stdout.strip():
        raise ProviderError(f"ffprobe could not read {path}: {result.stderr.strip()}")
    return float(result.stdout.strip())
