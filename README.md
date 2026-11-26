# The Window

A short film of about 80 seconds, narrated in Amharic with English subtitles, and the pipeline that makes it.

Two old men share a room in a home for the elderly. One has the bed by the only window, and every afternoon he describes the world outside to the friend who cannot sit up. The film is adapted from a widely shared parable ("The Hospital Window") and reset in a fictional home in Addis Ababa.

The pipeline turns one file, `storyboard.json`, into narration, pictures, music and a finished edit in vertical (9:16) and horizontal (16:9). Change one shot in that file, run one command, and only that shot is regenerated.

## Run it

You need [uv](https://docs.astral.sh/uv/) and [FFmpeg](https://ffmpeg.org/) on your PATH. Nothing else.

```bash
git clone <this repository>
cd <this repository>
uv run film
```

`uv run film` validates the storyboard and runs every stage in order: narration, timing, keyframes, video, shots, film. The finished films are written to `outputs/film/the_window_9x16.mp4` and `outputs/film/the_window_16x9.mp4`.

**On a clean clone no keys are needed.** Everything the models generated is kept in `outputs/` with a fingerprint of the inputs that produced it. The run sees that nothing changed, makes zero model calls, re-renders the shot clips with FFmpeg and leaves both films in `outputs/film/`. Checked on a clean clone: about two minutes, and `runs.jsonl` did not grow by a line. The first run downloads the Python dependencies.

**To generate something new you need keys.** Copy `.env.example` to `.env` and fill it in:

| Key | Where to get it | Used for |
|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio, "Get API key" | Narration (speech) |
| `KAGGLE_USERNAME` and `KAGGLE_API_TOKEN` | Kaggle, Settings, API. The account must be phone-verified to get a GPU | Pictures, score and video on a free GPU |

Then edit `storyboard.json` and run `uv run film` again.

## Try it: change one shot

1. Open `storyboard.json` and change the `subtitle_en` of `shot_09`.
2. Run `uv run film`.
3. Every stage prints `cache hit` except the film itself, which is re-assembled with the new subtitle. No model is called and nothing is added to `runs.jsonl`.

Change `narration.text` of one shot instead and exactly one speech request is made, for that shot. Change one `keyframe_prompt` and exactly two images are sent to the GPU: that shot, in its two aspect ratios.

## Useful commands

```bash
uv run film --radio-cut             # narration over a placeholder bed on a black screen: the story prototype
uv run film --only narration        # one stage: validate, narration, radio-cut, keyframes, music, video, shots, film
uv run film --only keyframes --shot shot_03
uv run film --aspect 9:16           # build one aspect ratio
uv run film --wait-for-quota        # when a free allowance runs out, wait as long as the provider says and continue
uv run film --only keyframes --collect   # pick up a GPU job that is already running instead of starting one
uv run film --force --only film     # ignore the cache for the stage that runs
uv run python -m pipeline.smoke     # call each provider once and log the latency
uv run python -m pipeline.costs     # rebuild COSTS.md from runs.jsonl
uv run pytest                       # about 110 tests, no network needed
```

## What it does, stage by stage

| Stage | Model or tool | Where it runs | Output |
|---|---|---|---|
| Narration | Gemini 3.8 Flash TTS | Gemini API, free tier | one WAV per shot |
| Timing | none | local | the timeline, cut to the measured voice |
| Keyframes | FLUX.2 klein 4B | Kaggle, two Tesla T4 | a reference portrait per character, then one image per shot per aspect ratio |
| Score | ACE-Step 1.5 | Kaggle | three candidates; one is chosen by ear |
| Video (optional) | Wan 2.2 TI2V-5B | Kaggle | short clips for the shots marked `video` |
| Shots | FFmpeg | local | one clip per shot: the video clip, or a slow camera move over the keyframe |
| Film | FFmpeg | local | both films: subtitles, end card, score ducked under the voice, −14 LUFS |

[ARCHITECTURE.md](ARCHITECTURE.md) explains the contract, the caching rules and what happens when something fails.

## What it costs

No money. Every model ran on a free tier or a free GPU. What it costs is time and patience: a free GPU job waits in a queue for about fifteen minutes before it starts, and the free speech allowance is ten requests in a rolling window. Measured latency, GPU minutes and a list-price equivalent are in [COSTS.md](COSTS.md), which is generated from the run log.

## Where things are

| File | What it is |
|---|---|
| `storyboard.json` | The contract: audience, characters, and for each shot its reason, narration, prompts, seed and camera move |
| `schema/storyboard.schema.json` | JSON Schema for the storyboard, checked before every run |
| `pipeline/` | One module per stage, plus `common.py` (cache, log, retries), `kaggle_jobs.py` and `run.py` (the command) |
| `gpu_jobs/` | The three scripts that run on Kaggle |
| `runs.jsonl` | One line per model call: model, parameters, seed, latency, GPU seconds, status |
| `outputs/` | Everything generated, kept so a run can be inspected and reused |
| `tests/` | The tests, on a frozen sample storyboard |
| [DESIGN.md](DESIGN.md) | Audience, intent, why each shot exists, the audience tests and what they changed |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Stages, contracts, caching, GPU jobs, failure handling |
| [EXPERIMENTS.md](EXPERIMENTS.md) | Hypothesis, change, result, decision |
| [FAILURES.md](FAILURES.md) | What broke, what was tried, what fixed it |
| [COSTS.md](COSTS.md) | Measured latency, GPU minutes, list-price equivalent |
| [ETHICS.md](ETHICS.md) | Consent, the story's source, labelling, licences |

## About the film

All three characters and the home are fictional. No real person or organisation is shown or voiced, and the voice is a stock synthetic voice. The film ends on a "Made with AI" card that is drawn in code. The project began as a different story, "Our Fridays"; [DESIGN.md](DESIGN.md) records why it changed, and `outputs/archive/` keeps that work.
