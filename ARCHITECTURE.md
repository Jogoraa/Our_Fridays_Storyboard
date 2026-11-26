# Architecture

## The idea

One file, `storyboard.json`, is the contract. Every stage is a module that reads it and writes files into `outputs/`. No stage calls another stage to get its data; it reads the files that stage left behind. That is what makes it possible to change one shot and regenerate only that shot, and it is why the whole film could be changed from one story to another on 25 November without touching a stage (DESIGN.md, decision log).

```
storyboard.json
      │ validate (schema + rules)
      ├──► narration ──► timing ──────────────┐
      │    one WAV per shot    cut to the voice │
      ├──► keyframes ──► video (optional) ──► shots ──► film
      │    references first,   Wan 2.2 on      clip per   9:16 and 16:9,
      │    then one image per  chosen shots    shot per   subtitles, end card,
      │    shot per ratio                      ratio      mixed sound
      └──► music ───────────────────────────────────────┘
           three candidates, one chosen
```

`uv run film` runs them in that order. `pipeline/run.py` is the only place that knows the order.

## The contract

`schema/storyboard.schema.json` (JSON Schema 2020-12, version 1.1) is checked before every run, and `pipeline/validate.py` adds the rules a schema cannot express:

- shot ids are unique and in order;
- every character a shot names exists;
- every music cue points at a real shot;
- both aspect ratios are present;
- planned length is 60 to 90 seconds including the end card;
- every shot has a `reason`.

What lives in the storyboard: the audience and intent, each character's description and approved reference, the style block, and for every shot its reason, narration (Amharic text and English subtitle), keyframe prompt, motion prompt, camera move, seed and whether each aspect ratio is a still or a video. Also the narrator's voice, style and tempo, the music caption, tempo, key, cues, candidates and the chosen score. A run can be explained by reading one file.

One thing deliberately does not live there: final timing. Planned durations are hints. The real timeline is computed from the measured length of each narration clip (`pipeline/timing.py`) and written to `outputs/timing_<lang>.json`, because picture is cut to the voice.

## Stages

| Stage | Module | Reads | Calls | Writes |
|---|---|---|---|---|
| validate | `validate.py` | storyboard, schema | nothing | nothing; stops the run on error |
| script | `script.py` | English lines | Gemini text | Amharic proposals for a person to approve. Never edits the storyboard. Used for the first story only |
| narration | `narration.py`, `split.py` | narration text, voice, style | Gemini TTS, one request per shot | `outputs/narration/<lang>/shot_XX.wav`, `durations.json` |
| timing | `timing.py` | measured durations, tempo | nothing | `outputs/timing_<lang>.json` |
| keyframes | `keyframes.py`, `gpu_jobs/flux_keyframes.py` | characters, style block, prompts, seeds | FLUX.2 klein 4B on a Kaggle T4 | `outputs/references/`, `outputs/keyframes/shot_XX_<ratio>.jpg` |
| music | `music.py`, `gpu_jobs/acestep_score.py` | caption, tempo, key, film length | ACE-Step 1.5 on a Kaggle T4 | `outputs/music/score_seed*.flac` |
| video | `video.py`, `gpu_jobs/wan_i2v.py` | keyframes, motion prompts | Wan 2.2 TI2V-5B on a Kaggle T4 | `outputs/video/shot_XX_<ratio>.mp4` |
| shots | `shots.py` | keyframes, video clips, timing | FFmpeg | `outputs/clips/shot_XX_<ratio>.mp4`, exactly as long as the timeline says |
| film | `assemble.py`, `subtitles.py` | clips, narration, score, timing | FFmpeg | `outputs/film/<slug>_9x16.mp4` and `_16x9.mp4` |

### Narration

One request and one file per shot, so a re-take costs one request and the clip is aligned with its shot by construction. Recording the whole film in one request and cutting it at pauses is implemented (`--one-take`, `split.py`) but is not the default: on a real take it put one cut a sentence early (EXPERIMENTS E1 to E3). Every take is checked before it is kept: longer than half a second, not silent, and, for split takes, a speaking pace within 1.3 times the median.

### Keyframes and consistency

Consistency comes from what the model is given each time, because it remembers nothing:

1. A reference portrait is generated for each character first, three candidates each. One is approved and named in the storyboard (`characters[].reference_asset`).
2. Every keyframe is conditioned on the references of the characters in that shot, shrunk to 512 pixels on the long side (FAILURES F14).
3. Every prompt ends with the same style block. A shot may carry its own (`style_block` on the shot): the two imagined scenes are warmer than the room and the white wall is flat and grey, on purpose.
4. The seed is in the storyboard, so a prompt change can be compared fairly.

Portrait and landscape keyframes are generated separately at 864x1536 and 1536x864. Neither is cropped from the other.

### Shots: video where it earns its place, a moving still everywhere else

`shots.py` produces one clip per shot per aspect ratio. If the storyboard says `video` and a Wan clip exists, the clip is conformed to the shot's length (slowed by at most a quarter, then held on its last frame). Otherwise the keyframe gets one slow camera move (`camera_move`: push in, pull out, pan, tilt or static) with FFmpeg's `zoompan`, rendered on a canvas twice the output size to hide the stepping. A shot asked to be video with no clip falls back to the still and says so.

### Film

FFmpeg only, so the same inputs give the same film. Per aspect ratio: concatenate the clips and a black end card, fade in, fade to the card, burn in one ASS file that holds the subtitles and the end-card text, and mix the sound. The mix places each narration clip at its start time (speeded by `tempo` without changing pitch), ducks the score under the voice with `sidechaincompress` (threshold 0.02, ratio 6, attack 300 ms, release 1500 ms), and normalises to −14 LUFS with two-pass `loudnorm` (measure, then correct linearly) at a true-peak setting of −1.5 dB so the encoded file stays under −1 dB (EXPERIMENTS E9).

All on-screen text is drawn here, never generated inside an image. Subtitles are at most two lines of 40 characters, timed in proportion across each shot's narration, with a bottom margin of 18% of the height in portrait and 10% in landscape.

## GPU jobs

Images, music and video need a GPU, and the free one is on Kaggle. `pipeline/kaggle_jobs.py` treats a job as: bake a manifest (the list of things to make) into a script from `gpu_jobs/`, push it as a private kernel, poll until it finishes, download `/kaggle/working`.

Three rules came out of using it (FAILURES F9, F14; EXPERIMENTS E10):

- **One job per stage run.** A job waits in a queue for about fifteen minutes however small it is, so every missing image goes into the same job.
- **Each output is saved as it is made,** with a `report.json` updated after every item. A session that dies keeps what it finished.
- **Retries live inside the job.** If an image runs out of memory the job frees the GPU and tries again smaller, because a second job would cost another queue.

`--collect` picks up a job that is already running instead of starting a new one, so closing the terminal does not lose it.

## Caching

Each output has a key: a SHA-256 hash of the stage name, the stage's code version, everything that decides the result (model, prompt or text, voice, seed, size, parameters) and the content hashes of any input files. The key is stored beside the output in `<file>.meta.json`.

Before a stage does work it computes the key and compares. Same key and a non-empty file: skip, print `cache hit`, make no model call. Anything different: regenerate.

Consequences, each pinned by a test:

- Editing one shot's narration line makes one speech request, for that shot. (`test_editing_one_line_calls_only_that_shot`)
- Editing one keyframe prompt sends two images to the GPU, that shot in its two ratios, with the approved references travelling inside the manifest. (`test_changing_one_keyframe_prompt_regenerates_only_that_shot`)
- Choosing a different reference for one character regenerates only the shots that character is in. (`test_choosing_a_different_reference_regenerates_that_characters_shots_only`)
- A new keyframe re-renders only that shot's clip. (`test_second_render_is_a_cache_hit_and_a_new_keyframe_rerenders_only_that_shot`)
- The film's key includes the hashes of every clip, narration file and the score, so it is re-assembled whenever any of them changes and never otherwise.

Two details that matter:

- A keyframe's key uses its references' keys, not their file hashes. A keyframe planned in the same job as its reference would otherwise look out of date the moment the reference file arrived.
- For narration and script the key leaves the model out. A take from the fallback model is still a valid take; which model made it is recorded in the meta file.

Outputs are written to a temporary file and renamed, and the meta file is written last. A run killed halfway leaves no meta file, so a half-written output is never mistaken for a finished one.

## The run log

`runs.jsonl` has one line per model call attempt: time, stage, shot, provider, model, parameters (the full prompt or text), seed, attempt number, latency, GPU seconds where a GPU was used, status (`ok`, `retry`, `failed`), error, output path and cost. For GPU stages there is one line per image, clip or track with the seconds it took on the GPU, plus one line for the job with the time from push to download. Cache hits are not model calls and are printed, not logged. Anything that looks like a key or token is masked. Paths are relative to the repository.

`uv run python -m pipeline.costs` turns the log into COSTS.md.

## Failure handling

- **Retries.** Every hosted call goes through `call_with_retry`: up to three attempts. A rate limit waits as long as the provider says in its error; other transient errors back off 2 s then 4 s. Only failures worth repeating are retried: rate limits, server errors, network errors and empty results. A bad request fails at once.
- **Quota.** A used-up allowance raises `QuotaError` and is not retried at once. The stage moves to the fallback model, and with `--wait-for-quota` waits the time the provider states, once, and continues. Because every finished shot is cached, a run stopped by quota resumes where it left off.
- **Fallbacks.** Text: `gemini-3.8-flash` then `gemini-3.5-flash-lite`. Speech: `gemini-3.8-flash-tts` then `gemini-3.8-flash-lite-tts`. Video: a moving still. Score: the placeholder bed, labelled as such.
- **Bad output that looks like success.** Speech that is too short or silent is retried and never cached. A split take with an implausible pace is rejected. A GPU item with no file is logged as failed and tried again on the next run.
- **Configuration.** A missing key or missing FFmpeg stops the run with one line naming what is missing. No request is sent and nothing is logged.
- **Timing.** If the measured narration makes the film longer than 90 s or shorter than 60 s, the run stops before assembly and prints each shot's length.

## Secrets

Keys are read from `.env`, which is git-ignored. `.env.example` lists the names. No key is written to logs, outputs or documents.

## Checked from a clean clone

On 26 November the repository was cloned into an empty folder with no `.env` and `uv run film` was run once. It exited 0 in 2 minutes 5 seconds. `runs.jsonl` had 225 lines before and 225 after: no model was called. Narration, references, keyframes and the score were cache hits; the 22 shot clips, which are not kept in the repository because FFmpeg re-renders them identically, were rendered again; both films were present at the end.

## Tests

`uv run pytest` runs about 106 tests in about 90 seconds with no network. Hosted calls and GPU jobs are replaced by fakes that return generated audio or small files; FFmpeg is real, so the radio cut and the film are actually assembled in both aspect ratios and their length, frame size and loudness are measured. The tests use a frozen sample storyboard (`tests/fixtures/storyboard.json`), so they do not change when the film does.
