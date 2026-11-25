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
