# The Window — report (draft)

> **How to use this draft.** The facts, numbers and file references below are taken from the repository and are accurate as of 25 November. The parts marked **[YOURS]** are about your reasons, your audience and what you learned. Only you can write those, in your own words, and the interview will ask about them. Delete this note and the markers before submitting. Export as PDF or Word.

## 1. What I set out to make, and for whom

**[YOURS: two or three sentences. Why this story. Who you pictured watching it.]**

Facts you can use:

- The film is "The Window", about 81 seconds, narrated in Amharic with English subtitles, in 9:16 and 16:9.
- It is adapted from a widely shared parable usually called "The Hospital Window" (often credited to Harry Buschman). I moved it from a hospital to a home for the elderly in Addis Ababa and wrote the narration in Amharic. I do not claim the story as my own invention (ETHICS.md).
- Audience as written in DESIGN.md before anything was generated: young Ethiopian adults who grew up around elders, watching on a phone.
- Intent: they should feel how much a small, invented kindness can carry, and leave wanting to give someone hope.
- I started with a different story, "Our Fridays", built the pipeline and a radio cut around it, and then changed. **[YOURS: why you changed. One honest paragraph. This is a strong part of your story: the brief asked for something that matters to you, and you noticed the first story did not.]**
- Because the storyboard is the only contract between stages, changing the film meant rewriting one file. No stage's code changed (DESIGN.md decision log, FAILURES F13).

## 2. What I learned from my audience

**[YOURS, after both tests. For each test: who the three people were (described, not named), what they said, and what you changed because of it. Point to the lines in DESIGN.md.]**

Structure to fill in:

- Test 1, the radio cut (narration only, black screen, `outputs/film/radio_cut_am.mp4`): ...
- What changed in `storyboard.json` because of it: ...
- Test 2, the near-final film: ...
- What changed because of it: ...

If a test did not change anything, say so and say why. Do not invent feedback: the interview asks what your audience told you.

## 3. The hardest problem and how I solved it

Recommended: **getting 22 keyframes out of a free GPU** (FAILURES F14, EXPERIMENTS E13). It is the best-documented struggle in the repository and it has a clear arc.

- The plan was Cloudflare's hosted FLUX. Its free daily allowance was already used up before the first call (F8), so the image model had to run as open weights on Kaggle's free T4s.
- Job 1: nine reference portraits were made, then all 22 keyframes failed with `CUDA out of memory. Tried to allocate 16.23 GiB`.
- First diagnosis: the two full-size reference images. I shrank them to 512 pixels and added cleanup between images. Job 2 failed the same way.
- The second report showed what the first had not: 12.6 GB of the 15 GB card was in use before a keyframe even started, because the text encoder and the image model were taking turns on one GPU. I had fixed a real problem and assumed it was the problem.
- Job 3 spread the two models over Kaggle's two GPUs. Ten of 22 succeeded, in an exact pattern: every one-character shot worked, every two-character shot and every no-character shot failed.
- I stopped trying to explain and used what had been measured to work: no-character shots in single-GPU mode (which had already made the portraits), and two-character shots with both people in one side-by-side reference image. Job 4 made all twelve.
- Along the way Kaggle rejected one upload with a bare HTTP 400 because the script had grown past 1 MB with embedded images (F15).
- Cost: four jobs, about 97 GPU minutes and most of an afternoon, for 31 images. The working configuration would take about 55 minutes.

**[YOURS: one or two sentences on what this taught you. For example, what you would check first next time.]**

Other candidates if you prefer: the ten-request speech limit and the one-take recording that cut a sentence into the wrong shot (F6, F10, E1 to E3); or Amharic running 95 seconds against a 90-second limit (F11, E6, E7).

## 4. A suggested practice that beat my instinct, and one that did not

**One that helped: a reference sheet before keyframes.**
Evidence: `outputs/references/sheet.jpg`, then the keyframes in `outputs/keyframes/`. Kebede appears in six shots (lying down, eyes closed, straining toward the window, turning to the caregiver, in tears) and is the same man in each. Without the approved portrait each prompt would have described "a bald old man with a grey moustache" from scratch. Changing a character's approved reference regenerates only that character's shots (`test_choosing_a_different_reference_regenerates_that_characters_shots_only`).

**[YOURS: was your instinct to go straight to shots? Say so if it was.]**

**One that also helped, and can be mentioned: a JSON contract between stages.** It is why the story could change in an afternoon.

**One that did not hold up as suggested: generating narration "line by line" as the cheap, flexible option.**
The brief says one file per shot makes re-takes cheap. On the free tier it is the opposite: the speech model allows ten requests in a rolling window, and an eleven-shot film needs eleven (F6). I tried the alternative, one request for the whole film cut at the pauses, and that failed differently: it put a sentence in the wrong shot, which only a pace measurement caught (E1 to E3, F10). I ended up keeping per-shot recording, but with a fallback voice model, a wait-for-quota mode and caching so a run resumes where it stopped. So the practice survived, but not for the reason given, and only with machinery around it.

Alternative candidate for "did not help": the brief's stack table. Cloudflare for keyframes, "Flash-Lite for bulk calls" and `make film` each failed on first contact (F8, F4, F3).

**[YOURS: pick the one you actually felt, and say it in your words.]**

## 5. Ceiling work

What exists in the repository beyond the floor:

- **A second language, measured.** The first story was recorded in both English and Amharic with the same voice. English ran at 0.075 to 0.098 seconds per character, Amharic at 0.131 to 0.166; the same eight lines were 78.6 s as a film in English and 95.0 s in Amharic (E7). The fallback text model's Amharic had an Arabic letter inside a word and invented words (E5, F7). A budget in words or characters taken from English guidance does not transfer.
- **A measured map of what fits on two free T4s** for FLUX.2 klein: nine configurations with outcome, seconds and peak memory (E13).
- **A cost report generated from the log** rather than written by hand (`pipeline/costs.py`).
- **A check that catches plausible-but-wrong output:** the speaking-pace test that rejected a mis-cut narration (E3).

**[YOURS: which of these changed your mind about something? The brief says one well-measured experiment that changed your mind is worth more than five features.]**

Not done: a frontier comparison (no access without billing), a song with lyrics, a LoRA, packaging as a tool.

## 6. What I would build next

**[YOURS. Some honest options from where the project stands:]**

- Video for more shots. Wan 2.2 ran out of memory on the first attempt (F16); the shots are slow camera moves over stills.
- One voice model for the whole film. Quota forced two (E4).
- An automatic check for extra people in two-character keyframes (E14 found one by eye).
- A small web form so a relative can type a story and get a storyboard to edit.

## Numbers to quote (regenerate with `uv run python -m pipeline.costs`)

- Model-call attempts logged in `runs.jsonl`: 208, of which 123 did not succeed (overload, quota, memory).
- Keyframes: 4 GPU jobs, 96.6 GPU minutes, 40 images made, mean 103 s per image on a T4.
- Score: 3 candidates in 23 s of generation; 3.2 GPU minutes including setup.
- Film: 81.1 s, −14.15 LUFS, true peak −1.43 dB, both aspect ratios.
- Tests: about 110, about 90 seconds, no network.
- Money spent: 0.
