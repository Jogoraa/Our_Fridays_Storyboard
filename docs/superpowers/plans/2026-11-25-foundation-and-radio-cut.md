# Foundation and Radio Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repository where `uv run film --radio-cut` validates `storyboard.json`, generates per-shot Amharic narration with Gemini TTS, and assembles a narrated, placeholder-scored, subtitled black-screen cut, with caching, retries and `runs.jsonl` logging.

**Architecture:** One contract (`storyboard.json`, schema 1.1). Each stage is a module in `pipeline/` that reads the contract and writes to `outputs/`. A shared core provides content-hash caching (sidecar `.meta.json`), a retry wrapper that logs every model call, and FFmpeg helpers. Keyframes, shots, real music and the final edit are later plans.

**Tech Stack:** Python 3.14, uv, `jsonschema`, `httpx`, `python-dotenv`, `pytest`, FFmpeg 9 as a subprocess, Gemini API (text + TTS).

**Spec:** `docs/superpowers/specs/2026-11-25-our-fridays-pipeline-design.md`

## Global Constraints

- Run command is `uv run film`; flags `--radio-cut`, `--only <stage>`, `--shot <id>`, `--lang <am|en>`, `--force`.
- All file I/O is UTF-8 (`encoding="utf-8"`); Amharic text must survive Windows.
- Secrets only from `.env` / environment. `.env` is git-ignored. No key is ever logged or printed.
- `runs.jsonl` gets one line per real model call (every attempt). Cache hits print to the console only.
- Retries: 3 attempts, exponential backoff, on rate-limit and server errors only.
- Final film total 60–90 s including the end card; target 80–85 s with a 3 s end card.
- Nothing in DESIGN.md, EXPERIMENTS.md, FAILURES.md or COSTS.md is written unless it happened.
- Provider model ids are verified against current docs before first use; a moved model is recorded in FAILURES.md.
- Local commits after each task. No push and no public repo until Abu says to publish.

## Review Focus

1. A key missing from `.env`: the run stops with one line naming the variable, no traceback, no partial outputs. (Task 2)
2. A run interrupted mid-write: the half-written file is never treated as cached. Outputs are written to a temp name and renamed; meta is written last. (Task 2)
3. TTS returns empty or near-silent audio with HTTP 200: treated as a retryable failure, not cached. (Task 5)
4. Editing one shot's narration line: exactly one new TTS call, for that shot. (Task 5)
5. Measured narration pushes the total past 90 s: the run reports the overrun and per-shot durations and stops before assembly, rather than exporting an invalid film. (Task 4)

---

## File structure

```
pyproject.toml              project, deps, script entry film = pipeline.run:main
pipeline/__init__.py
pipeline/common.py          paths, env, cache, run log, retry, ffmpeg helpers
pipeline/validate.py        schema + semantic validation
pipeline/timing.py          narration durations -> shot timeline
pipeline/gemini.py          Gemini text and TTS HTTP calls
pipeline/smoke.py           one call per configured provider
pipeline/script.py          drafts Amharic lines for approval
pipeline/narration.py       per-shot TTS stage
pipeline/music.py           placeholder pad (FFmpeg, not a model)
pipeline/subtitles.py       ASS subtitle file from timing
pipeline/assemble.py        radio cut
pipeline/run.py             CLI
tests/                      test_validate, test_common, test_timing, test_narration, test_subtitles
```

---

### Task 1: Project scaffold, schema 1.1, validation

**Files:** Create `pyproject.toml`, `pipeline/__init__.py`, `pipeline/validate.py`, `tests/test_validate.py`. Modify `schema/storyboard.schema.json`, `storyboard.json`.

**Interfaces — Produces:**
- `class StoryboardError(Exception)`
- `validate_storyboard(sb: dict) -> None` (raises `StoryboardError` with a readable message)
- `load_storyboard(path: Path | None = None) -> dict` (reads UTF-8, validates, returns)

Schema 1.1 changes from the starter: `schema_version` const `"1.1"`; `project_status` enum `draft | radio_cut | rough_cut | final`; top-level `style_block` (string), `audience` (string), `intent` (string), `narration_voice` (`{voice, style_instruction}`); `music` becomes `{status, caption, tempo_bpm, key, candidates, chosen, mix_direction, cues[]}` with cue `{at_seconds, direction}`; `end_card.duration_seconds` number; each shot: rename `purpose` to `reason`; replace `narration_en`/`subtitle_source_en` with `narration: {text, lang, source_en, subtitle_en}`; add `camera_move` enum `push_in | pull_out | pan_left | pan_right | tilt_up | tilt_down | static`; `render: {"9:16": still|video, "16:9": still|video}`; optional `overlay_text` (array of `{text, at_fraction}`).

Migration of `storyboard.json`: `narration.text` starts as the English line with `lang: "en"` until Amharic is approved (Task 5).

- [ ] **Step 1:** `git init`, write `pyproject.toml` (requires-python >=3.12; deps jsonschema, httpx, python-dotenv; dev dep pytest; `[project.scripts] film = "pipeline.run:main"`), `uv sync`.
- [ ] **Step 2: failing tests** in `tests/test_validate.py`:
  - `test_repo_storyboard_is_valid`: `load_storyboard()` returns a dict with 8 shots.
  - `test_unknown_character_rejected`: shot lists `"nobody"` → `StoryboardError` mentioning `nobody`.
  - `test_duplicate_or_unordered_shot_ids_rejected`.
  - `test_missing_reason_rejected`: delete a shot's `reason` → `StoryboardError`.
  - `test_planned_total_outside_60_90_rejected`.
- [ ] **Step 3:** run `uv run pytest tests/test_validate.py -v`, expect failures.
- [ ] **Step 4:** update schema and storyboard, implement `validate.py`.
- [ ] **Step 5:** tests pass. Commit.

### Task 2: Core — cache, run log, retry, FFmpeg helpers

**Files:** Create `pipeline/common.py`, `tests/test_common.py`.

**Interfaces — Produces:**
- `ROOT: Path`, `OUTPUTS: Path`, `RUNS_PATH: Path`
- `class ConfigError(Exception)`, `class RetryableError(Exception)`, `class ProviderError(Exception)`
- `require_env(name: str) -> str` (loads `.env` once; raises `ConfigError("Missing NAME in .env")`)
- `sha256_file(path: Path) -> str`
- `cache_key(stage: str, version: str, payload: dict, input_files: Sequence[Path] = ()) -> str` — SHA-256 of canonical JSON (`sort_keys=True, ensure_ascii=False`) of `{stage, version, payload, inputs: [file hashes]}`
- `is_cached(output: Path, key: str) -> bool` — output exists, non-empty, and `<output>.meta.json` has the same key
- `write_output(output: Path, data: bytes, key: str, meta: dict) -> None` — temp file, rename, then meta
- `mark_output(output: Path, key: str, meta: dict) -> None` — meta only, for files FFmpeg wrote
- `log_run(record: dict, path: Path = RUNS_PATH) -> None` — adds UTC `ts`, appends one JSON line
- `call_with_retry(fn: Callable[[], T], *, stage: str, provider: str, model: str, params: dict, shot: str | None = None, seed: int | None = None, attempts: int = 3, base_delay: float = 2.0, sleep=time.sleep, log_path: Path = RUNS_PATH) -> T` — logs every attempt with `attempt`, `latency_s`, `status` (`ok | retry | failed`), `error`; retries only `RetryableError`; raises `ProviderError` after the last
- `run_ffmpeg(args: list[str]) -> None` (raises `ProviderError` with stderr tail; `ConfigError` if FFmpeg is not on PATH)
- `probe_duration(path: Path) -> float`

- [ ] **Step 1: failing tests** (all use `tmp_path`):
  - `test_cache_key_changes_with_payload_and_input_file`
  - `test_cache_key_stable_for_reordered_dict_and_amharic_text`
  - `test_is_cached_false_without_meta` (file exists, no meta — Review Focus 2)
  - `test_is_cached_false_for_empty_file`
  - `test_write_output_then_is_cached_true`
  - `test_retry_succeeds_on_third_attempt_logs_three_lines` (statuses `retry, retry, ok`)
  - `test_retry_gives_up_after_three_and_raises_provider_error` (last status `failed`)
  - `test_non_retryable_error_is_not_retried` (one line logged)
  - `test_log_run_never_contains_key_material`: params containing `api_key` → value replaced by `"***"`
  - `test_require_env_missing_names_the_variable` (Review Focus 1)
- [ ] **Step 2:** run, expect failures. **Step 3:** implement. **Step 4:** pass. **Step 5:** commit.

### Task 3: Gemini client and smoke test

**Files:** Create `pipeline/gemini.py`, `pipeline/smoke.py`.

**Interfaces — Produces:**
- `generate_text(prompt: str, *, model: str, temperature: float = 0.3) -> str`
- `synthesize(text: str, *, model: str, voice: str, style_instruction: str) -> bytes` — returns WAV bytes (wraps the API's raw PCM in a WAV header at the sample rate the response declares); raises `RetryableError` on 429/5xx/timeouts, `ProviderError` on other errors
- `pipeline.smoke.main() -> int` — for each provider whose keys are present, one minimal call through `call_with_retry` (stage `smoke`); prints a table of provider, model, latency, status; skipped providers are listed as skipped

- [ ] **Step 1:** look up the current Gemini text and TTS model ids, request shape and Amharic support in the Gemini API docs; record anything that differs from the brief in FAILURES.md.
- [ ] **Step 2:** implement `gemini.py` and `smoke.py` (Gemini only for now; Cloudflare and Kaggle rows are added by their own plans).
- [ ] **Step 3:** run `uv run python -m pipeline.smoke`. Expected: Gemini text and TTS rows `ok` with latencies, matching lines in `runs.jsonl`. Commit.

### Task 4: Timing

**Files:** Create `pipeline/timing.py`, `tests/test_timing.py`.

**Interfaces — Produces:**
- `class TimingError(Exception)`
- `build_timing(sb: dict, durations: dict[str, float], *, lead: float = 0.4, tail: float = 0.7) -> dict` returning `{"shots": [{"id", "start", "duration", "narration_start", "narration_duration"}], "end_card": {"start", "duration"}, "total"}`; shot duration = `lead + narration + tail`, rounded to whole frames at 24 fps; shots are contiguous; end card follows the last shot
- `check_total(timing: dict, lo: float = 60.0, hi: float = 90.0) -> None` — raises `TimingError` listing per-shot durations and the overrun in seconds

- [ ] **Step 1: failing tests:** `test_shots_are_contiguous_and_frame_aligned`; `test_narration_starts_after_lead`; `test_total_includes_end_card`; `test_overrun_raises_with_per_shot_breakdown` (Review Focus 5); `test_missing_duration_for_a_shot_raises`.
- [ ] **Step 2–4:** fail, implement, pass. **Step 5:** commit.

### Task 5: Script draft and narration stage

**Files:** Create `pipeline/script.py`, `pipeline/narration.py`, `tests/test_narration.py`.

**Interfaces — Consumes:** Task 2 core, Task 3 `generate_text`, `synthesize`, Task 4 `build_timing`.
**Produces:**
- `script.run(sb: dict, *, force: bool = False) -> Path` — one Gemini text call per shot translating `narration.source_en` into natural spoken Amharic for a warm narrator; writes `outputs/script/<shot>.am.json` (`{source_en, proposed_am}`) and a combined `outputs/script/proposal.md` for Abu to read. Does not modify `storyboard.json`.
- `narration.run(sb: dict, *, lang: str | None = None, only_shot: str | None = None, force: bool = False, synth=gemini.synthesize) -> dict[str, float]` — per shot: key from `{text, lang, model, voice, style_instruction}`; if cached, print `cache hit` and skip; else call through `call_with_retry`, reject audio shorter than 0.5 s or with RMS below a silence threshold as `RetryableError`, write `outputs/narration/<lang>/<shot>.wav`; returns measured durations and writes `outputs/narration/<lang>/durations.json`.

- [ ] **Step 1: failing tests** (fake `synth` returning a generated tone WAV, `tmp_path` outputs and log):
  - `test_first_run_calls_once_per_shot`
  - `test_second_run_makes_no_calls`
  - `test_editing_one_line_calls_only_that_shot` (Review Focus 4)
  - `test_silent_audio_is_retried_and_not_cached` (Review Focus 3)
  - `test_only_shot_limits_calls`
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5:** run `script.run`, give Abu `outputs/script/proposal.md`; after he approves or edits the Amharic, write it into `storyboard.json` (`narration.text`, `lang: "am"`).
- [ ] **Step 6:** run the narration stage for real; Abu listens to shot 1 before the rest is trusted. Commit.

### Task 6: Placeholder music, subtitles, radio cut, CLI

**Files:** Create `pipeline/music.py`, `pipeline/subtitles.py`, `pipeline/assemble.py`, `pipeline/run.py`, `tests/test_subtitles.py`.

**Interfaces — Produces:**
- `music.placeholder(duration: float) -> Path` — `outputs/music/placeholder.wav`, a quiet two-chord sine pad with slow fades, made by FFmpeg, cached on duration. Not a model call; labelled a placeholder everywhere.
- `subtitles.wrap(text: str, max_chars: int = 40, max_lines: int = 2) -> list[str]` — list of cues, each at most two lines of 40 characters, split at sentence or clause boundaries
- `subtitles.build_ass(sb: dict, timing: dict, *, width: int, height: int) -> str` — cues spread across the shot's narration window in proportion to their length; bottom margin 18% of height in portrait, 10% in landscape
- `assemble.radio_cut(sb: dict, timing: dict, *, lang: str) -> Path` — `outputs/film/radio_cut_<lang>.mp4`: black 1080x1920 at 24 fps, narration clips placed with `adelay` at each `narration_start`, pad ducked with `sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500`, subtitles burned in, two-pass `loudnorm` to I=-14, TP=-1; H.264 + AAC
- `run.main(argv: list[str] | None = None) -> int` — order: validate → narration → timing (`check_total`) → placeholder → radio cut when `--radio-cut`; `ConfigError`, `StoryboardError`, `TimingError`, `ProviderError` print one line and return 1

- [ ] **Step 1: failing tests:** `test_wrap_never_exceeds_two_lines_of_40`; `test_wrap_keeps_all_words_in_order`; `test_build_ass_cues_stay_inside_narration_window`; `test_portrait_margin_larger_than_landscape`.
- [ ] **Step 2–4:** fail, implement, pass.
- [ ] **Step 5:** run `uv run film --radio-cut`. Verify with `ffprobe`: duration equals `timing.total` within one frame, one video and one audio stream; measured integrated loudness within 1 LU of −14; a second run reports cache hits and adds no lines to `runs.jsonl`.
- [ ] **Step 6:** start README, ARCHITECTURE, FAILURES, EXPERIMENTS, COSTS, ETHICS with only what is true so far; update DESIGN.md audience and intent. Commit. Hand the radio cut to Abu for the first audience test.
