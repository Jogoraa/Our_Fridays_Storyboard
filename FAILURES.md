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
- **Resolution:** In progress. The narration stage is being changed to record the whole film in one call and split it into per-shot files, keeping single-shot calls for re-takes. See EXPERIMENTS.md once it has run.

## F7. The Amharic draft contained non-words and an Arabic letter

- **When:** 25 November. Evidence: `outputs/script/candidates/gemini-3.5-flash-lite/`.
- **What broke:** The fallback model's Amharic had an Arabic letter inside an Amharic word (shot 4, "ላك"), invented words (shot 3 "ኩኩራ", shot 8 "አንባርቆሹ"), a wrong noun (shot 7, "ፌጦ", a plant, for "packet") and lost the word "Fridays", the film's title, in shot 7.
- **What I tried:** Asked two stronger models for the same lines to compare. Both were unavailable (503, then the daily limit), so there is no comparison yet.
- **Workaround:** The model draft is kept as evidence. A corrected version is written out line by line in `outputs/script/amharic_for_review.md`, and nothing is recorded until the author, a native speaker, approves each line.
- **Lesson:** A small model can produce Amharic that looks plausible to a non-reader and is wrong. The script stage only proposes; a person approves.
