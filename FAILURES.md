# Failures — what broke, what was tried, what fixed it

Newest last. Only things that actually happened are recorded here.

## F1. The Gemini speech API in the brief had moved

- **When:** 25 November, before the first call.
- **What broke:** The brief's link (`ai.google.dev/gemini-api/docs/speech-generation`) redirects to `aistudio.google.com/docs/speech-generation`, and the API it describes is no longer the `generateContent` call with `responseModalities` that most examples online still show. Speech is now on the Interactions API: `POST /v1beta/interactions`, with the style in a `speech_metadata` annotation and the voice in `generation_config.speech_config`.
- **What I tried:** Read the current page in full instead of writing the call from memory.
- **What fixed it:** `pipeline/gemini.py` is written against the current shape. Two details mattered: the text is spoken verbatim, so the style instruction must go in `speech_metadata.style` and not in the text; and a normal request now returns a complete WAV file, where older models returned raw PCM that had to be wrapped. The client checks for the `RIFF` header rather than assuming.
- **Lesson:** Model ids and request shapes go stale within months. The model ids are read from the environment (`GEMINI_TTS_MODEL`, `GEMINI_TEXT_MODEL`) with defaults, so the next move is a one-line change.

## F2. A missing API key was logged as a failed model call

- **When:** 25 November, first run of `uv run film --radio-cut` with an empty `.env`.
- **What broke:** The run stopped, correctly, but the message was wrapped as `gemini gemini-3.8-flash-tts: Missing GEMINI_API_KEY`, and a line with `status: failed` was written to `runs.jsonl`. No request had been sent, so the log claimed a model call that never happened.
- **What I tried:** Wrote a test first (`test_config_error_is_not_logged_as_a_model_call`) and watched it fail.
- **What fixed it:** The retry wrapper now lets configuration errors pass straight through, unlogged. The false line was removed from `runs.jsonl`. The message is now one line: `error: Missing GEMINI_API_KEY in .env (see .env.example)`.
- **Lesson:** `runs.jsonl` is evidence. A line in it has to mean a request really left the machine.

## F3. `make film` is not available on this machine

- **What broke:** The brief suggests `make film`. This is Windows without `make`.
- **What fixed it:** The one command is `uv run film`, a console script declared in `pyproject.toml`. It behaves the same on Windows, macOS and Linux and needs only `uv` and FFmpeg.

## F4. The text model was overloaded, and the fallback model in the brief does not exist

- **When:** 25 November, first script-draft run. Evidence: `runs.jsonl`, stage `script` and `smoke`, model `gemini-3.8-flash`, status `retry`/`failed` with `HTTP 503 ... currently experiencing high demand`.
- **What I tried:** Three attempts with backoff per shot. All failed. Added a fallback to the lighter model the brief names, "Gemini 3.8 Flash-Lite".
- **What broke next:** `HTTP 404: Model 'gemini-3.8-flash-lite' not found. Did you mean 'gemini-3.5-flash-lite'?` There is a 3.8 Flash-Lite for speech (`gemini-3.8-flash-lite-tts`) but not for text.
- **What fixed it:** Listed the models the key can actually use (`GET /v1beta/models`) instead of guessing, and set the fallback to `gemini-3.5-flash-lite`. `pipeline/script.py` now tries each model in turn; `tests/test_script.py` pins the behaviour. All eight lines were drafted by the fallback.

## F5. The retry logic burned the daily quota

- **When:** 25 November, same session.
- **What broke:** After the 503s, calls began failing with `HTTP 429 ... limit: 5 requests per minute on Free Tier`, then `limit: 20 requests per day on Free Tier. Please retry in 56m50s`. The free text model allows 20 requests a day. My retries had spent them: `runs.jsonl` shows 35 attempts against `gemini-3.8-flash` and not one success. Worse, the wrapper kept retrying the daily limit with 2 s and 4 s waits, which could never work.
- **What I tried:** Read the error bodies in the log rather than treating every 429 the same.
- **What fixed it:** Three changes, each with a test written first:
  1. A per-minute limit is retried after the delay the provider asks for (`Please retry in 12s` is parsed, plus one second), not after a fixed backoff.
  2. A per-day limit raises `QuotaError` and is never retried; the stage falls back to another model or stops with a clear message.
  3. The delay parser handles `12s`, `56m50s` and `1h2m3s`.
- **Lesson:** On a free tier a retry is not free. A retry policy has to know which errors can clear in seconds and which cannot.

## F6. Speech is limited to 10 requests a day, which breaks "one call per shot"

- **When:** 25 November, first real narration call.
- **What broke:** `HTTP 429: Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier)`. The plan was one speech call per shot: eight calls per language, sixteen for Amharic plus the English comparison, before any re-take. That does not fit in ten.
- **What I tried:** Checked whether other speech models have their own allowance. `gemini-3.8-flash-lite-tts` answered (5.5 s of Amharic audio) while the main model was refusing, so quotas are per model. `gemini-3.1-flash-tts-preview` rejected the request: `Speech metadata is not supported for this model`, so it cannot take the same style instruction.
- **Resolution:** Three things together. Recording the whole film in one request was tried and rejected (EXPERIMENTS E1, E2). The stage falls back to the lighter voice model, which has its own allowance. And the limit turned out to be a rolling window, not a calendar day: the error says when a slot frees up, so with `--wait-for-quota` the stage waits that long and carries on. Because every finished shot is cached, a run that stops on quota resumes where it left off.

## F7. The Amharic draft contained non-words and an Arabic letter

- **When:** 25 November. Evidence: `outputs/script/candidates/gemini-3.5-flash-lite/`.
- **What broke:** The fallback model's Amharic had an Arabic letter inside an Amharic word (shot 4, "ላك"), invented words (shot 3 "ኩኩራ", shot 8 "አንባርቆሹ"), a wrong noun (shot 7, "ፌጦ", a plant, for "packet") and lost the word "Fridays", the film's title, in shot 7.
- **What I tried:** Asked two stronger models for the same lines to compare. Both were unavailable (503, then the daily limit), so there is no comparison yet.
- **Workaround:** The model draft is kept as evidence. A corrected version is written out line by line in `outputs/script/amharic_for_review.md`, and nothing is recorded until the author, a native speaker, approves each line.
- **Lesson:** A small model can produce Amharic that looks plausible to a non-reader and is wrong. The script stage only proposes; a person approves.

## F8. Cloudflare's free image allowance was already gone

- **When:** 25 November, the first image request of the project.
- **What broke:** `HTTP 429: you have used up your daily free allocation of 10,000 neurons`. This project had not made a single Cloudflare call; something else on the same account had used the day's allowance. It resets at 00:00 UTC.
- **What I tried:** The Gemini image models on the same key (`gemini-3.1-flash-image`, `gemini-2.5-flash-image`, `gemini-3.1-flash-lite-image`): all `429 You exceeded your current quota`, which on a free key means no quota at all.
- **What fixed it:** Changed provider. FLUX.2 klein 4B is open-weight (Apache 2.0), so the keyframes stage runs it on a Kaggle T4 instead of calling Cloudflare. The stage takes a `runner`, so a hosted API can be put back with one function.
- **Lesson:** A shared free account is a shared quota. Open weights on a borrowed GPU are slower to start but nobody else can spend them.

## F9. Kaggle: an old client, then a long queue

- **What broke first:** `uvx kaggle` ran a cached old client that crashed with `ModuleNotFoundError: No module named 'six'`.
- **Fix:** pin the invocation to `uvx --with six kaggle@latest` in `pipeline/kaggle_jobs.py`.
- **What broke next:** the first GPU job sat in `QUEUED` for many minutes. A seven-second script took 941 s from push to output (EXPERIMENTS E10).
- **Workaround:** one job for all images; a `--collect` flag that picks up a job already running, so closing the terminal does not lose it; each image saved as it finishes.

## F10. One long take, cut in the wrong place

- **What broke:** Recording all lines in one request and splitting at pauses produced eight clips with one cut a sentence early (EXPERIMENTS E2). Nothing crashed; the files looked fine.
- **How it was caught:** not by ear. Shot 3 ran at 0.073 s per character and shot 4 at 0.143 while the rest were near 0.11.
- **Fix:** the pace check was tightened so that this exact case is rejected automatically (E3), the misaligned clips were set aside in `outputs/archive/our_fridays/narration/am_one_take_rejected/`, and all eight shots were recorded one by one.
- **Lesson:** A stage needs a check that can fail on output that is plausible but wrong.

## F11. Amharic ran 96 seconds

- **What broke:** `error: film would run 95.0 s, 5.0 s over the 90 s limit`, with each shot's length listed. The same story in English was 78.6 s.
- **Fix:** a pitch-preserving tempo of 1.10 on the voice, set in the storyboard (EXPERIMENTS E6, E7). The check that stopped the build is `timing.check_total`; it runs before any assembly so an invalid film is never exported.

## F12. Backslashes eaten on the way to disk

- **What broke:** Subtitle override tags such as `{ad(250,200)}` were written into `pipeline/subtitles.py` with a single backslash, so Python read `` as a form-feed character. The tests that existed still passed, because they only looked for the visible text.
- **How it was caught:** printing one generated subtitle line showed it ending at `{`.
- **Fix:** corrected the source, and added `test_ass_contains_override_tags_and_no_control_characters`, which fails if any control character reaches the subtitle file.
- **Lesson:** The tool that writes a file can change it. Test the bytes that matter, not just the words.

## F13. The story changed after the pipeline was built

- **What happened:** With the radio cut of "Our Fridays" finished, the author replaced the story with "The Window" (DESIGN.md, decision log).
- **What it cost:** eleven new narration requests against a ten-request window, and every test that had quietly depended on the film's own storyboard (shot count, character names) would have broken.
- **Fix:** tests now load a frozen sample storyboard (`tests/fixtures/storyboard.json`); one test checks the live storyboard is valid. The character-specific wording in the keyframe prompt ("the woman from reference image 1") became a `noun` field on each character. No stage needed a code change beyond that.

## F14. Every keyframe ran out of GPU memory

- **When:** 25 November, first picture job on Kaggle. Evidence: `runs.jsonl`, stage `keyframes`, 22 lines with status `failed`; the job's own report is kept at `outputs/references/v1/job_report.json`.
- **What broke:** The nine reference portraits were made (about 85 s each, peak 12.5 GB of the T4's 15 GB). The first keyframe then failed with `CUDA out of memory. Tried to allocate 16.23 GiB`. After that every remaining image failed within 0.02 s with `Tried to allocate 20.00 MiB ... 4.81 MiB is free`, including the three shots that use no reference at all.
- **Two causes:**
  1. A keyframe was conditioned on two reference portraits at full size (864x1152 each). The model attends over the tokens of the picture being made plus the tokens of every reference, and attention memory grows with the square of that count. Two full references more than doubled the tokens: roughly 13,000 instead of 5,200.
  2. The job caught the error and went on, but the failed attempt's tensors were still referenced by the exception, so `torch.cuda.empty_cache()` freed nothing and one failure took down the other 21 images.
- **What fixed it (`gpu_jobs/flux_keyframes.py`):**
  - References are shrunk to 512 pixels on the long side before conditioning. They only need to carry a face and clothes. That brings the token count to about 6,700.
  - Before every image the job runs `gc.collect()` and empties the cache, and it drops the exception object before retrying.
  - A retry ladder: if memory still runs out, try 384-pixel references, then the picture itself at five sixths of the size. The size actually used is recorded per image in `runs.jsonl` (`made_at`, `reference_side`, `failed_attempts`).
- **Cost of the failure:** 944 s of GPU session and about an hour of waiting, for nine usable images.
- **Lesson:** "Keep going after an error" is only safe if the error leaves the GPU clean. And a job that takes fifteen minutes to start needs its own retries inside it.

### F14, second attempt: the first fix was not the cause

- **What happened:** The job with smaller references and cleanup between images failed the same way: nine portraits made, 22 keyframes out of memory (`outputs/references/job2_report.json`, three attempts recorded per image).
- **What the report showed this time:** Before the first keyframe had allocated anything, the error read `12.64 GiB is allocated by PyTorch` and only 1.7 GB was free. The keyframe needed 4.68 GB more. So the shortage was not mainly the references. The text encoder and the image model are about 8 GB each, and in the memory-saving mode they take turns on one 15 GB card; what stays resident between turns left too little for a picture a third larger than the portraits. After the first failure the two models were both left on the card (14.4 GB allocated), which is why every later image failed in under a second whatever its size.
- **I had fixed a real problem (reference size) and assumed it was the problem.** The first report did not include how much memory was already in use, so the first diagnosis was a guess that fitted. The job now records every attempt's full error.
- **Fix:** Kaggle gives two T4s and the job was using one. The pipeline is now loaded with `device_map="balanced"`, which puts the text encoder on one card and the image model on the other, so nothing takes turns. If only one GPU is present the job falls back to the old mode and, before each image, sends every model back to the CPU (`maybe_free_model_hooks`) so that one failure cannot poison the next image. The placement used is written to the job report.
- **Cost so far:** two failed jobs, about 33 minutes of GPU session and two hours of elapsed time, for references only.
