# Architecture

## The idea

One file, `storyboard.json`, is the contract. Every stage is a script that reads it and writes files into `outputs/`. No stage calls another stage's code to get its data; it reads the files that stage left behind. That is what makes it possible to change one shot and regenerate only that shot.

```
storyboard.json ──► validate ──► script ──► narration ──► timing ──► keyframes ──► shots ──► music ──► assemble
   (contract)        schema      Amharic     one WAV      cut to      one image     clip or    score     both films
                     + rules     drafts      per shot     the voice   per shot      moving
                                                                      per ratio     still
```

Built so far: validate, script, narration, timing, the placeholder music bed and the radio cut. Keyframes, shots, the real score and the final edit are next and will be described here as they are built.

## The contract

`schema/storyboard.schema.json` (JSON Schema 2020-12, version 1.1) is checked before every run, and `pipeline/validate.py` adds the rules a schema cannot express:

- shot ids are unique and in order;
- every character a shot names exists;
- every music cue points at a real shot;
- both aspect ratios are present;
- planned length is 60–90 seconds including the end card;
- every shot has a `reason`.

Prompts, seeds, the narrator's voice and style, camera moves, on-screen phone text and the music caption all live in the storyboard, not in code. A run can be explained by reading one file.

One thing deliberately does not live there: final timing. Planned durations are hints. The real timeline is computed from the measured length of each narration clip (`pipeline/timing.py`) and written to `outputs/timing_<lang>.json`, because picture is cut to the voice.

## Stages

| Stage | Module | Reads | Calls | Writes |
|---|---|---|---|---|
| validate | `validate.py` | storyboard, schema | nothing | nothing; stops the run on error |
| script | `script.py` | English lines | Gemini text | `outputs/script/` Amharic proposals for the author to approve. Never edits the storyboard |
| narration | `narration.py` | narration text, voice, style | Gemini TTS, one call per shot | `outputs/narration/<lang>/shot_XX.wav`, `durations.json` |
| timing | `timing.py` | measured durations | nothing | `outputs/timing_<lang>.json` |
| music (placeholder) | `music.py` | length | FFmpeg synthesis | `outputs/music/placeholder.wav` |
| assemble (radio cut) | `assemble.py`, `subtitles.py` | narration, bed, timing | FFmpeg | `outputs/film/radio_cut_<lang>.mp4` |

Assembly uses only FFmpeg, which is deterministic: the same inputs give the same film. The mix places each narration clip at its start time, ducks the music under the voice with `sidechaincompress`, and normalises to −14 LUFS with a true peak of −1 dB using two-pass `loudnorm` (measure first, then correct linearly).

## Caching

Each output has a key: a SHA-256 hash of the stage name, the stage's code version, everything that decides the result (model, prompt or text, voice, seed, parameters) and the content hashes of any input files. The key is stored beside the output in `<file>.meta.json`.

Before a stage does work it computes the key and compares. Same key and a non-empty file: skip, print `cache hit`, make no model call. Anything different: regenerate.

Consequences:

- Editing shot 3's narration line changes one key. One TTS call is made, for shot 3. The assembly key includes the hashes of its input files, so the film is re-assembled; nothing else is touched.
- Changing the narrator's voice changes every narration key, so all eight regenerate. That is correct.
- Outputs are written to a temporary file and renamed, and the meta file is written last. A run killed halfway leaves no meta file, so the half-written output is never mistaken for a finished one.

Tests pin each of these: `tests/test_common.py` and `tests/test_narration.py`.

## The run log

`runs.jsonl` has one line per model call attempt: time, stage, shot, provider, model, parameters, seed, attempt number, latency, status (`ok`, `retry`, `failed`), error and output path. Cache hits are not model calls and are printed, not logged. Anything that looks like a key or token in the parameters is masked before writing.

## Failure handling

- **Retries.** Every provider call goes through `call_with_retry`: up to three attempts with exponential backoff (2 s, 4 s). Only failures worth repeating are retried: rate limits (429), server errors (5xx), network errors and empty results. A bad request (4xx) fails at once.
- **Bad output that looks like success.** A speech response that is under half a second long or silent is treated as a failure and retried, and is never cached.
- **Configuration.** A missing key or missing FFmpeg stops the run with one line naming what is missing. No request is sent and nothing is logged.
- **Timing.** If the measured narration makes the film longer than 90 s or shorter than 60 s, the run stops before assembly and prints each shot's length, so the fix (a shorter line) is obvious.
- **Fallbacks** for images, video and music are described with those stages when they are built.

## Secrets

Keys are read from `.env`, which is git-ignored. `.env.example` lists the names. No key is written to logs, outputs or documents.

## Tests

`uv run pytest` runs 49 tests in about 25 seconds with no network access. Provider calls are replaced by a fake that returns generated audio; FFmpeg is real, so the radio cut is actually assembled and its length and loudness are measured.
