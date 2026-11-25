# Our Fridays — film pipeline design

Date: 2026-11-25. Deadline for both submissions: Thursday 26 November 2026, 23:59 East Africa Time.

## Intent and why

Dawit  is submitting "B2W0: AI-Content Generation" (brief: `AI-Content Generation.pdf`, "The Heritage Short"). He wants the highest mark he can get on both assignments, each out of 100:

1. Codebase and report, graded by reading code, text, logs and documents only (no media is opened), followed by an AI interview.
2. Film (50), walkthrough video (30), public post (20), graded by hand.

The film is "Our Fridays", a fictional story Abu wrote: two friends, Rahel and Bekele, an unspoken love, a move to another city, and a promise to keep their Friday coffee. The starter folder holds a storyboard draft (8 shots, 84 s + 4 s end card), a schema and a design worksheet. No pipeline, media or logs exist yet.

The brief weighs process as heavily as the film. So the thing being built is a small, honest, reproducible studio in code, and the film is its output.

## Goals

- One documented command, `uv run film`, regenerates the film from `storyboard.json` on a clean clone.
- A 60–90 s film in 9:16 (1080x1920, the main submission) and 16:9 (1920x1080): clear narration, original score ducked under the voice, accurate burned-in English subtitles, consistent characters and style, a visible "Made with AI" end card.
- Five stages around one validated contract, each a script that reads `storyboard.json` and writes to `outputs/`.
- Re-runs regenerate only what changed. Changing one shot's prompt or narration line produces exactly one new model call for that asset, visible in `runs.jsonl`.
- Every model call logged; retries; fallbacks; no secrets in the repo.
- The document set the brief lists: README, ARCHITECTURE, DESIGN, EXPERIMENTS (at least ten real entries), FAILURES, COSTS, ETHICS.
- A complete, submittable film exists early, and gets better shot by shot.

## Non-goals

- A web app, MCP server, LoRA training, or a song with lyrics.
- Paid frontier models (need a payment card; a frontier comparison is only required "where you had access").
- Remotion. Titles and the end card are done in FFmpeg.

## Anti-goals (would make this a failure even if it runs)

- Invented evidence. Audience feedback, experiments, failures, latencies and costs are only ever written from things that actually happened. Sections waiting on Abu stay marked pending.
- A repository Abu cannot explain in the interview. Code stays small and plain; ARCHITECTURE.md explains every choice.
- Ending the day with video clips but no finished film.

## Constraints

- About 36 hours. Windows 11, no local GPU, no `make`. Python 3.14, uv, FFmpeg 9 (full build), git and gh are installed.
- No provider keys yet. Abu supplies a Gemini API key, a Cloudflare account ID plus Workers AI token, and a Kaggle API token in a local `.env`.
- Free tiers only: Cloudflare daily image allowance (roughly 50–170 images), Kaggle about 30 GPU hours a week on T4s, with queues and session timeouts.
- Only Abu can do: two audience tests with at least three real people each, the walkthrough recording, the public post, the report's personal reflections, the interview, and a native-speaker listen to the Amharic narration.
- Model names in the brief (Gemini 3.8 Flash TTS, FLUX.2 klein, FLUX.1 schnell, Wan 2.2 TI2V-5B, ACE-Step 1.5) must be checked against current provider docs at build time; anything that has moved goes in FAILURES.md.

## Approaches

1. **Stills first, then upgrade to video. Chosen by Abu.** Build the whole pipeline with every shot as a keyframe plus a slow FFmpeg camera move, giving a finished film within hours. Then replace assets one at a time with Wan 2.2 clips from Kaggle as the queue allows. Always submittable; each upgrade is a logged experiment; matches the per-shot regeneration the walkthrough must show. Cost: some shots may stay as moving stills.
2. **Full video from the start.** All shots through Wan 2.2 before any assembly. Most motion if it works, but a free T4 takes many minutes per clip and one failure near the deadline leaves no film.
3. **Paid frontier models.** Dropped: needs a payment card and the brief does not reward it.

## Decided with Abu

- Approach 1.
- The story is fiction he wrote, made for this assignment. No real person is shown or voiced.

## My calls (Abu can overrule any of these)

- **Audience:** young Ethiopian adults — Abu's friends and cohort colleagues on Slack — watching on a phone. "The assignment" cannot be the audience because the brief needs two tests with three real people each. Intent: they recognise the feeling of something left unsaid, and leave warmed that the friendship continues.
- **Language:** Amharic narration, English subtitles. An English narration track is generated as a measured comparison (the one piece of ceiling work).
- **Run command:** `uv run film`, with `--radio-cut`, `--only <stage>`, `--shot <id>`, `--aspect <9:16|16:9>`.
- **Python**, standard library plus `jsonschema`, `httpx`, `python-dotenv`; FFmpeg called as a subprocess.

## Design

### Repository shape

```
README.md  ARCHITECTURE.md  DESIGN.md  EXPERIMENTS.md  FAILURES.md  COSTS.md  ETHICS.md
storyboard.json            the contract
schema/storyboard.schema.json
pipeline/                  common.py (cache, log, retry, ffmpeg helpers), validate.py,
                           script.py, narration.py, keyframes.py, shots.py, music.py,
                           assemble.py, run.py (the one command)
kaggle/                    Wan 2.2 and ACE-Step job scripts that run on Kaggle
runs.jsonl                 one line per model call, committed
outputs/                   references/ keyframes/ clips/ narration/ music/ film/, committed
tests/                     schema, cache-key and timing tests
.env.example  .gitignore   (.env ignored)
```

### The contract: storyboard.json, schema 1.1

Extends the starter. Additions: `project_status` becomes an enum (draft, radio_cut, rough_cut, final); `style_block` (fixed prompt text appended to every image prompt); each shot gets `narration` (`text` in Amharic, `subtitle_en`, and the English source line), `reason` (the existing `purpose`), `camera_move` for the still fallback (e.g. push_in, pan_left, static), `render` per aspect ratio (`still` or `video`), optional `overlay_text` for phone messages added in the edit, and `seed`; a top-level `music` block with caption, tempo, key, candidates and a `cues` list with timecodes; `end_card`. Planned durations stay as hints. Real timing is derived from measured narration and written to `outputs/timing.json`. Validation runs before every stage and also checks things JSON Schema cannot: shot order, character ids exist, total length 60–90 s after timing.

### Stages

| Stage | Reads | Model / tool | Writes |
|---|---|---|---|
| script | English lines | Gemini Flash: drafts Amharic lines and checks subtitle length (2 lines, about 40 characters) | `outputs/script/` proposals for Abu to approve into the storyboard |
| narration | narration text, style | Gemini Flash TTS, one file per shot | `outputs/narration/shot_XX.wav`, measured durations, `timing.json` |
| keyframes | characters, style block, prompts, seeds | Cloudflare Workers AI: FLUX.2 klein with reference images, FLUX.1 schnell as fallback | character/style reference sheet first, then one keyframe per shot per aspect ratio |
| shots | keyframes, motion prompts, `render` | Wan 2.2 TI2V-5B on Kaggle for `video`; FFmpeg zoompan for `still` | `outputs/clips/shot_XX_<aspect>.mp4` |
| music | music block | ACE-Step 1.5 on Kaggle, three candidates; a quiet FFmpeg-synthesised pad as radio-cut placeholder | `outputs/music/` candidates and the chosen score |
| assemble | everything above, timing | FFmpeg only | radio cut, then both films |

Each asset is addressed by (shot, aspect ratio), so a shot can be video in portrait and a moving still in landscape. Portrait is upgraded first because it is the main submission.

Assembly: trims clips to timing, concatenates at a constant 24 fps, burns subtitles from a generated ASS file with safe margins per aspect ratio, draws phone-message text and the end card in code, ducks the score with `sidechaincompress` (starting at threshold 0.02, ratio 6, attack 300 ms, release 1500 ms), runs two-pass `loudnorm` to −14 LUFS with true peak −1 dB, and exports H.264 + AAC MP4.

### Caching

Every asset has a key: a SHA-256 of the stage's code version, the model id, parameters, prompt text, seed and the hashes of its input files. The key is stored in a sidecar `.meta.json` beside the output. If the key matches, the stage skips and no model call is made. Editing shot 3's keyframe prompt changes the key for shot 3's keyframes only, which in turn changes the key for shot 3's clips and for the final assembly. Nothing else regenerates.

### Logging, retries, failure handling

`runs.jsonl` gets one line per real model call: timestamp, stage, shot, aspect, provider, model, parameters, seed, attempt, latency, GPU seconds where known, list-price cost equivalent, status, output path, error. Cache hits print to the console and are not model calls.

Each call is tried up to three times with exponential backoff on rate limits and server errors. After that the stage falls back: klein to schnell for images; video to moving still for shots; placeholder pad for music. A fallback is recorded in `runs.jsonl` and never fails the run silently.

Kaggle jobs are pushed and polled through the Kaggle API from the `shots` and `music` stages. The Kaggle scripts save each output as it finishes so a timed-out session keeps its work. On a clean clone without Kaggle credentials, cached clips in `outputs/` are reused when their keys match and stills are used otherwise; the README says so plainly.

### Order of work, with an approval between stages

1. Today: repo, schema 1.1, validation, logging and caching, a smoke test of each provider, narration, radio cut. **Abu plays the radio cut to three people and gives me their words.**
2. Today/tonight: storyboard changes from that feedback, reference sheet, keyframes, a complete stills film in both aspect ratios, Kaggle jobs for music and the first video upgrades running overnight.
3. Tomorrow morning: chosen score, video upgrades, near-final cut. **Abu runs the second test.**
4. Tomorrow afternoon: final export, all documents from the real logs, GitHub push. Abu writes the post and report reflections (I draft structure and facts), records the walkthrough, submits.

## Rules settled after review (my calls unless marked)

- **If Amharic fails.** English narration is an acceptable final film; the brief allows any language. Abu decides after hearing the first Amharic narration. If Gemini TTS rejects Amharic outright, the film goes English and the failure is written up.
- **If the film runs long.** The end card counts inside the 60–90 s. Target is 80–85 s total with a 3 s end card. I may tighten pauses and padding myself. Cutting or rewording a line or dropping a shot is Abu's: I propose the trim and he approves it.
- **Who judges look and sound.** I choose by stated criteria (same face and wardrobe as the reference, clean hands and faces, no stray text; for the voice, clear names and calm pace; for the score, no lead melody fighting the voice) and record each choice with its reason. Abu reviews in three batches: the radio cut, a contact sheet of references and keyframes, and the near-final cut. If he is away, I proceed with my pick and he can overrule it later; the cache makes that a cheap redo.
- **Keyframes versus feedback.** The reference sheet starts immediately. Shot keyframes wait for the first test's feedback, or three hours, whichever comes first, to protect the daily image allowance.
- **Clean clone with no keys.** `uv run film` rebuilds both films from committed `outputs/` whose cache keys match: zero model calls, real FFmpeg assembly. With keys, `--force` or any storyboard edit triggers live generation. Each committed media file stays well under GitHub's 100 MB limit.
- **No Kaggle GPU.** Music falls back to ACE-Step on Colab or a hosted Space, then to the synthesised pad as a last resort, stated honestly in FAILURES.md. Shots stay as moving stills.
- **Testers' privacy.** DESIGN.md records testers as short descriptions (for example "friend, 24, designer"), never names, with their words quoted only as Abu reports them.
- **Repository.** Public GitHub repository under Abu's account, created with `gh` when he says to publish.

## Appendix: the rubric this is planned against

Brief: "AI-Content Generation: The Heritage Short", 23 pages, in the shared Drive folder.

Assignment 1 (code, text, logs, documents; media not opened; AI interview follows):
- Software engineering and reproducibility, 20: stage boundaries around a validated `storyboard.json`; caching so re-runs regenerate only what changed; retries; no secrets; complete `runs.jsonl`; one documented command from a clean clone.
- Documentation, 10: README a stranger can follow; ARCHITECTURE.md on contracts, caching, failure handling.
- Design thinking and audience, 10: audience and intent stated before generating; written notes of two tests (radio cut, near-final cut), each with at least three audience members; storyboard visibly changed by them; every shot has a stated reason.
- Experimentation and iteration: at least ten logged experiments with hypotheses, evidence in text or logs, reasons for each choice.
- Troubleshooting and persistence: FAILURES.md with real blockers (quota, memory, consistency, language), what was tried, how resolved.
- Measurement, 5: latency and GPU minutes per stage, list-price equivalent, frontier comparison where access existed.
- Consent, labelling and licences, 5.
- Report, three criteria: reflection tied to repository evidence (audience, what changed, hardest problem); one suggested practice that beat instinct and one that did not, with evidence; ceiling work that produced insight.
- (The remaining 50 points are spread over the five criteria whose point values did not extract from the PDF.)

Assignment 2 (manual):
- Film, 50: 60–90 s in both aspect ratios; clear narration, ducked score, accurate subtitles; consistent characters and style; AI end card; a story that lands for the chosen audience.
- Walkthrough, 30: at most five minutes; architecture and one hard decision; one keyframe prompt or narration line changed, pipeline rerun, only that shot regenerated, shown on screen (logs with a single new model call count).
- Public post, 20: public, written by Abu: the story, why it matters to him, one thing learned; platform AI label on.
- Gate: a real person shown or voiced without a consent record scores the film zero.

Report contents: what was made and for whom; what the audience taught; hardest problem and its solution; the practice that helped and the one that did not; ceiling work; what to build next.

## Left to the builder

- Exact provider model ids and request shapes, verified against current docs.
- Gemini TTS voice and style instruction, chosen by experiment.
- Keyframe sizes each model accepts, and how the portrait keyframe is conditioned on the landscape one.
- Wan 2.2 draft and final resolution on a T4, and clip length.
- Subtitle font (must render Latin; Amharic only if phone overlays use it), sizes and margins.
- Which ten-plus experiments to run; they must be real single-variable comparisons with fixed seeds.
