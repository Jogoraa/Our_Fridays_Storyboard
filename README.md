# Our Fridays

A 60–90 second short film about two friends, an unspoken love and a promise to keep meeting, made by a pipeline that turns one file, `storyboard.json`, into narration, pictures, music and a finished edit.

**Status: in progress.** The contract, validation, narration, timing and the radio cut (narration over a placeholder bed on a black screen) are built and tested. Keyframes, moving shots, the score and the final edit are next.

## Run it

You need [uv](https://docs.astral.sh/uv/) and FFmpeg on your PATH.

```bash
git clone <this repository>
cd <this repository>
uv run film
```

That one command validates the storyboard and runs every stage in order. Each stage is cached, so:

- on a clean clone, outputs already in `outputs/` whose inputs have not changed are reused and no model is called;
- after you edit one shot in `storyboard.json`, only that shot's assets are regenerated, then the film is re-assembled.

To generate anything new you need API keys. Copy `.env.example` to `.env` and fill it in:

| Key | Where to get it | Used for |
|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio, "Get API key" | Script drafts and narration |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard, Workers AI | Keyframes |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | Kaggle, Settings, API | Video and music on a free GPU |

Useful variations:

```bash
uv run film --radio-cut            # stop after the narration-only prototype
uv run film --only narration       # one stage
uv run film --only narration --shot shot_03
uv run film --lang en              # build the English narration track instead
uv run film --force                # ignore the cache for the stages that run
uv run python -m pipeline.smoke    # call each provider once and log the latency
uv run pytest                      # 49 tests, no network needed
```

## What it costs

Nothing so far. Every model used runs on a free tier. Measured latency and GPU minutes per stage, with a list-price equivalent, are in [COSTS.md](COSTS.md).

## Where things are

| File | What it is |
|---|---|
| `storyboard.json` | The contract: shots, reasons, prompts, seeds, narration, voice, music cues |
| `schema/` | JSON Schema for the storyboard, checked before every run |
| `pipeline/` | One module per stage, plus `common.py` (cache, log, retries) and `run.py` (the command) |
| `runs.jsonl` | One line per model call |
| `outputs/` | Everything generated, kept so a run can be inspected |
| [DESIGN.md](DESIGN.md) | Audience, intent, the two audience tests and what they changed |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Stages, contracts, caching, failure handling |
| [EXPERIMENTS.md](EXPERIMENTS.md) | Hypothesis, change, result |
| [FAILURES.md](FAILURES.md) | What broke and what fixed it |
| [COSTS.md](COSTS.md) | Measured latency, GPU minutes, list-price equivalent |
| [ETHICS.md](ETHICS.md) | Consent, labelling, licences |

## The film

Fiction, written by the author. Narrated in Amharic with English subtitles, in vertical (9:16) and horizontal (16:9), ending on a "Made with AI" card. No real person is shown or voiced.
