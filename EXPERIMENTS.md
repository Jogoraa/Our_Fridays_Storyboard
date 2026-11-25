# Experiments

Each entry states a hypothesis, the one thing that was changed, what was measured and what was decided. Evidence is in `runs.jsonl` (stage, shot and model are given so the lines can be found), in files under `outputs/`, or in a test that pins the result.

Entries E1 to E10 were run on the first story, "Our Fridays", whose outputs are in `outputs/archive/our_fridays/`. The pipeline is the same for "The Window".

## E1. Can the whole film be narrated in one speech request?

- **Why:** The free speech model allows 10 requests in a rolling window (FAILURES F6). One request per shot uses 8 to 11 of them.
- **Hypothesis:** If every line is sent in one request with a `<long pause>` between lines, the take can be cut at its longest pauses into per-shot clips, and one request does the work of eight.
- **Change:** `--one-take` joins the lines; `pipeline/split.py` cuts at the N−1 longest silences.
- **Result:** Failed on the first real take. The model's pause between lines was 0.92 s, not clearly longer than its pauses at sentence ends inside a line, so the splitter refused (`runs.jsonl`: stage `narration`, mode `batch`, `could not split the take: ambiguous`). Two requests were spent for nothing.
- **Decision:** Length alone cannot find the line breaks. Led to E2.

## E2. Cutting the take where the text says each line should end

- **Hypothesis:** A line's share of the speaking time is close to its share of the characters, so each line break should be the pause nearest to that fraction of the speech.
- **Change:** `split_take(..., weights=[len(line) ...])` matches pauses to expected positions in order, minimising total distance (`_by_text` in `pipeline/split.py`). The raw take is now saved so a failed split can be studied without another request.
- **Result:** On the real Amharic take (`outputs/archive/our_fridays/narration/am/takes/`, 25 pauses between 0.3 s and 1.4 s) it returned eight clips. But the seconds-per-character of each clip gave it away: shot 3 came out at 0.073 s/char and shot 4 at 0.143, against about 0.11 for the others. A sentence from shot 3 had landed in shot 4. The two shots together were the right length; the cut between them was one pause early.
- **Decision:** Speaking pace is not uniform enough (quoted speech is slower) for position alone. One-take recording stays in the code as an opt-in, and per-shot recording is the default because it is aligned by construction. The saving was not worth a wrong cut.

## E3. How tight can the pace check be?

- **Hypothesis:** An automatic check on seconds-per-character can catch a misplaced cut like E2's without rejecting honest takes.
- **Change:** `PACE_TOLERANCE` from 2.5 to 1.3 (a clip may be at most 1.3 times faster or slower than the median).
- **Evidence:** Eight honest per-shot English takes ranged from 0.075 to 0.098 s/char, within 1.18 of their median. The bad split of E2 was 1.5 away. Both cases are pinned as tests with the measured numbers: `test_natural_variation_in_pace_is_accepted` and `test_a_split_that_puts_a_sentence_in_the_wrong_shot_is_rejected_by_the_pace_check`.
- **Decision:** 1.3. With the old value the wrong cut would have passed silently.

## E4. Does the lighter voice model read Amharic at the same pace?

- **Why:** When the main model's allowance runs out the stage falls back to `gemini-3.8-flash-lite-tts`. If the two read at different speeds, a film voiced by both would feel uneven.
- **Change:** Same voice (`Sulafat`), same style instruction, same language; shots 1 and 2 were voiced by the lighter model and shots 3 to 8 by the main one because of quota.
- **Result:** Lighter model 0.134 s/char on both shots. Main model 0.131 to 0.166 s/char, mean 0.152. Request latency: lighter 3.4 s, main 3.7 to 5.4 s for clips of 8 to 13 s.
- **Decision:** The main model is about 13% slower in delivery. For the final film all shots should come from one model; a mixed film is acceptable only for the radio cut. The model that voiced each clip is stored in its `.meta.json` so this can be checked.

## E5. Is the fallback text model good enough to draft Amharic narration?

- **Hypothesis:** `gemini-3.5-flash-lite` can translate eight short narration lines into natural Amharic.
- **Result:** Six of eight lines had errors a reader could see: an Arabic letter inside an Amharic word, two invented words, a wrong noun, a wrong gender, and the word "Fridays", the film's title, lost. Kept unedited in `outputs/archive/our_fridays/script/candidates/gemini-3.5-flash-lite/`. A comparison with two stronger models could not be run: both returned 503 and then the daily limit (FAILURES F4, F5).
- **Decision:** A model drafts; the author, a native speaker, writes and approves. For "The Window" no model drafted the Amharic at all.

## E6. Fitting a slow reader into 90 seconds

- **Problem:** The Amharic narration of the first story measured 84.7 s. With shot padding and the end card the film would run 95.0 s; the limit is 90.
- **Options considered:** cut words (the author's decision, and costs speech requests), ask the voice to speak faster (costs eight requests, effect unknown), or play the recorded voice slightly faster without changing its pitch (free, deterministic).
- **Change:** `narration_voice.tempo` in the storyboard, applied with FFmpeg `atempo`.
- **Result (measured total film length):** tempo 1.00 → 95.0 s; 1.06 → 90.3 s; 1.08 → 88.8 s; 1.10 → 87.4 s; 1.12 → 86.0 s.
- **Decision:** 1.10. It is the smallest value that leaves more than two seconds of margin. Whether it is audible is a question for the audience test.

## E7. The same story in English and in Amharic

- **Change:** language only; same eight lines, same voice and style, each recorded shot by shot.
- **Result:** English 66.6 s of speech, film 78.6 s. Amharic 84.7 s of speech, film 95.0 s before the tempo change. Per character, English ran at 0.075 to 0.098 s and Amharic at 0.131 to 0.166 s. Amharic words are longer to say per written character, so a character budget taken from English guidance (the brief suggests 130 to 220 words) does not transfer.
- **Decision:** Budget Amharic narration by measured seconds, not by word or character counts. "The Window" was written to about 560 Amharic characters for that reason.

## E8. Fixed backoff against the provider's own retry hint

- **Hypothesis:** Waiting the time the provider states succeeds where fixed 2 s and 4 s backoff does not.
- **Before:** 35 attempts against `gemini-3.8-flash` with fixed backoff, no success (`runs.jsonl`, stage `script`).
- **Change:** parse `Please retry in 6m40s` from the error; per-minute limits wait that long; "per day" limits are not retried immediately, and with `--wait-for-quota` the stage waits the stated time once and continues.
- **After:** the narration stage waited 4.8 minutes once and then recorded six shots in a row without a failure.
- **Decision:** Keep. Also learned: the "per day" limit behaves as a rolling window, so the hint, not the word "day", is what to trust.

## E9. True-peak target after AAC encoding

- **Hypothesis:** Normalising to a true peak of −1.0 dB leaves the encoded file under −1.0 dB.
- **Result:** No. With `TP=-1.0` the English radio cut measured −14.05 LUFS but a true peak of −0.87 dB after AAC encoding.
- **Change:** `TRUE_PEAK = -1.5`.
- **Result:** The Amharic radio cut measured −14.07 LUFS and −1.18 dB.
- **Decision:** −1.5 for the limiter so the delivered file is under −1.0. A test now requires the delivered peak to be below −0.5 dB.

## E10. What a free Kaggle GPU job really costs in time

- **Change:** pushed a seven-second script (`gpu_jobs/gpu_check.py`) that reports the hardware.
- **Result:** 941 s from push to downloaded output (`runs.jsonl`, stage `smoke`, provider `kaggle`), for 7.1 s of work. The rest was queueing and container start. Hardware: two Tesla T4 with 15 GB each, 20.9 GB of disk, internet on.
- **Decision:** Never send one image per job. The keyframes stage puts every missing image into a single job, and saves each image as it finishes.

## E11. Three score candidates, chosen under the voice

- **Why:** Every seed gives a different piece. A score is judged under the narration, not alone.
- **Change:** seed only (3101, 3102, 3103). Same caption, 64 BPM, D major, 87 s, instrumental, ACE-Step 1.5 turbo at 8 steps, one batch of three (`runs.jsonl`, stage `music`).
- **Measured** (`outputs/music/candidates_measured.json`):

| Seed | Integrated loudness (LUFS) | Loudness range | Voice band (300 Hz to 3 kHz) relative to full band |
|---|---|---|---|
| 3101 | -16.6 | 9.5 | -2.9 dB |
| 3102 | -18.8 | 6.8 | -2.9 dB |
| 3103 | -17.9 | 12.8 | -5.3 dB |

- **Hypothesis:** The candidate with the least energy in the voice's band will sit best under the narrator.
- **Result:** Each candidate was mixed under the real narration with the film's ducking and loudness settings (`outputs/music/audition_seed*.mp3`). The author listened to all three and chose 3103, the one the measurement pointed to. It is also the most dynamic of the three, which suits a piece that has to open up on the imagined garden and nearly stop on the white wall.
- **Decision:** `music.chosen = score_seed3103.flac` in the storyboard. The other two are kept.
- **Cost:** 23 s of GPU for all three; 194 s for the whole job including building ACE-Step's environment and downloading the model.
