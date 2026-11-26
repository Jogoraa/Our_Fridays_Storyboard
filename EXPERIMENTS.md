# Experiments

Each entry states a hypothesis, the one thing that was changed, what was measured and what was decided. Evidence is in `runs.jsonl` (stage, shot and model are given so the lines can be found), in files under `outputs/`, or in a test that pins the result.

Entries E1 to E10 were run on the project's first story, "Our Fridays", before the film became "The Window" (DESIGN.md, decision log). The pipeline is the same. Its audio and video were removed when the repository was cleaned up; what is kept in `outputs/archive/our_fridays/` is the text evidence these entries cite (measured durations, the model's unedited Amharic drafts, the old storyboard), and every call is still in `runs.jsonl`.

## E1. Can the whole film be narrated in one speech request?

- **Why:** The free speech model allows 10 requests in a rolling window (FAILURES F6). One request per shot uses 8 to 11 of them.
- **Hypothesis:** If every line is sent in one request with a `<long pause>` between lines, the take can be cut at its longest pauses into per-shot clips, and one request does the work of eight.
- **Change:** `--one-take` joins the lines; `pipeline/split.py` cuts at the N−1 longest silences.
- **Result:** Failed on the first real take. The model's pause between lines was 0.92 s, not clearly longer than its pauses at sentence ends inside a line, so the splitter refused (`runs.jsonl`: stage `narration`, mode `batch`, `could not split the take: ambiguous`). Two requests were spent for nothing.
- **Decision:** Length alone cannot find the line breaks. Led to E2.

## E2. Cutting the take where the text says each line should end

- **Hypothesis:** A line's share of the speaking time is close to its share of the characters, so each line break should be the pause nearest to that fraction of the speech.
- **Change:** `split_take(..., weights=[len(line) ...])` matches pauses to expected positions in order, minimising total distance (`_by_text` in `pipeline/split.py`). The raw take is now saved so a failed split can be studied without another request.
- **Result:** On the real Amharic take (25 pauses between 0.3 s and 1.4 s; `runs.jsonl`, stage `narration`, mode `batch`, model `gemini-3.8-flash-lite-tts`) it returned eight clips. But the seconds-per-character of each clip gave it away: shot 3 came out at 0.073 s/char and shot 4 at 0.143, against about 0.11 for the others. A sentence from shot 3 had landed in shot 4. The two shots together were the right length; the cut between them was one pause early.
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
- **Result:** Each candidate was mixed under the real narration with the film's ducking and loudness settings. The author listened to all three and chose 3103, the one the measurement pointed to. It is also the most dynamic of the three, which suits a piece that has to open up on the imagined garden and nearly stop on the white wall.
- **Decision:** `music.chosen = score_seed3103.flac` in the storyboard. The two that were not chosen were deleted in the clean-up; their measurements stay in `candidates_measured.json`, and `uv run film --only music` regenerates them from the same seeds.
- **Cost:** 23 s of GPU for all three; 194 s for the whole job including building ACE-Step's environment and downloading the model.

## E12. Does describing the characters more specifically change the reference portraits?

- **Why:** In the first set of portraits (`outputs/references/v1/sheet.jpg`) the two men could be read as South Asian rather than Ethiopian, and Hana, described as "in her late twenties", looked about forty.
- **Hypothesis:** Naming a region and features ("from the Amhara highlands, East African Habesha features") and giving an exact age ("27 years old, youthful face") will move the faces.
- **Change:** the character descriptions only. Same seeds (7001 to 7203), same model, same size, same style block.
- **Result** (`outputs/references/sheet.jpg` against `v1/sheet.jpg`): Hana changed clearly: younger, and her hair is braided as the new text says. The two men are almost pixel-for-pixel the same portraits as before. With the seed fixed, the extra ethnicity wording did nothing visible for them; the exact age and the hairstyle did.
- **Decision:** Concrete, visible attributes (age in years, hairstyle, clothing) steer this model; regional labels on their own do not. The approved references are Girma candidate 2, Kebede candidate 3 and Hana candidate 1, chosen for a clear, front-lit face. Whether the men read as Ethiopian was put to the author, who looked at the sheet and approved all three on 25 November. The audience test will ask the same thing.

## E13. What fits on two 15 GB T4s, measured

- **Why:** Three keyframe jobs failed on memory before one worked (FAILURES F14). This table is the result of those jobs, from the per-image reports kept in `outputs/references/` and logged in `runs.jsonl` (`made_at`, `reference_side`, `failed_attempts`, `gpu_seconds`).

| Image | Size | Model placement | References | Outcome | Seconds | Peak memory |
|---|---|---|---|---|---|---|
| Portrait, text only | 864x1152 | one GPU, taking turns | none | made, 18 of 18 | 85 to 92 | 12.5 GB |
| Keyframe | 864x1536 | one GPU, taking turns | two at 864 px | out of memory | - | wanted 16.2 GB more |
| Keyframe | 864x1536 | one GPU, taking turns | two at 512 px | out of memory | - | wanted 4.7 GB more |
| Keyframe | 864x1536 | two GPUs | one at 512 px | out of memory | - | - |
| Keyframe | 720x1280 | two GPUs | one at 384 px | made, 10 of 10 | 86 | 13.5 GB |
| Keyframe | 720x1280 | two GPUs | two at 384 px | out of memory | - | wanted 4.0 GB more |
| Keyframe | 720x1280 | two GPUs | none | out of memory | - | - |
| Keyframe | 720x1280 | one GPU, taking turns | none | made, 6 of 6 | 92 | 12.0 GB |
| Keyframe | 720x1280 | two GPUs | two people in one 320 px image | made, 6 of 6 | 177 | 13.5 GB |

- **Decision:** The last four rows are the configuration the job now uses. The 177 s for combined references includes one failed rung at 384 px each time; starting at 320 px would save about half of it.
- **What I would test next with more quota:** whether text-only images fail in two-GPU mode because of where the library places the image decoder. I did not need the answer to finish, so I did not spend a job on it.

## E14. Two references as one image: it fits, but the model may copy the layout

- **Hypothesis:** Putting both characters' references side by side in a single image carries both identities for the memory cost of one reference.
- **Change:** for shots with two characters, one combined reference and a prompt that says who is on the left and who is on the right.
- **Result:** All six such images were made, and in five the two people are the right two people in the right places (shots 1 and 10 in both ratios, shot 2 in landscape). In shot 2 portrait the model drew three men: Kebede lying down as asked, plus both men from the reference sitting side by side behind him. The reference's layout leaked into the picture. The rejected image is kept at `outputs/keyframes/rejected/shot_02_9x16_three_men.jpg`.
- **Fix tried:** one sentence added to shot 2's keyframe prompt: "Exactly two people in the picture: one man lying down, one man sitting up." Only shot 2 was planned for regeneration (two images, one job).
- **Result of the fix:** It did not work. The landscape image was right again and the portrait image again had three men (`outputs/keyframes/rejected/shot_02_9x16_three_men_second_try.jpg`). A sentence of text did not outweigh a reference image that shows two men sitting side by side, at least in a tall frame where there is room behind the foreground figure.
- **Second fix:** change the shot, not the wording. Shot 2 is now a picture of Kebede alone, flat on his back, with the window and Girma's folded shawl out of focus behind him. It uses a single reference, the path that has worked every time, and it fits the narration better: the line at that moment is about Kebede seeing only the ceiling. The storyboard's `characters`, `keyframe_prompt` and `reason` for shot 2 were edited and only shot 2 was regenerated. Result: one man, in both ratios, on the first rung (`runs.jsonl`, stage `keyframes`, shot `shot_02`, the last two lines for that shot). Only shot 2's two clips were re-rendered and the two films re-assembled.
- **Decision:** Keep the combined reference for shots where two people face the camera or each other (shots 1 and 10 are right in both ratios). Do not use it where one person is in the foreground and the other behind; give that shot one character. Check every two-character keyframe for extra people before it goes into the film.

## E15. Is real video worth its GPU time on a free T4?

- **Hypothesis:** Animating three single-character portrait shots with Wan 2.2 TI2V-5B will look better than a slow camera move over the keyframe, at a cost the quota can bear.
- **Change:** `render` set to `video` for shots 3, 6 and 11 in 9:16. Draft size 480x832, image-to-video from the keyframe, motion-only prompts. Second attempt, with the models spread over both GPUs (the first ran out of memory: FAILURES F16).
- **Result** (`runs.jsonl`, stage `video`; clips kept in `outputs/video/`):
  - All three clips were made, but only on the third rung of the retry ladder: 73 frames and 49 frames both ran out of memory (the card wanted 4.9 GB and then 2.3 GB more), and 33 frames at 20 steps fit, peak 13.4 GB.
  - Each clip took about 3,390 s on the GPU, 57 minutes, for 1.4 seconds of video. The job ran 10,550 s in total.
  - The clips are faithful: Girma's face, beard and shawl and Kebede's face and cardigan hold across all 33 frames, with a small natural movement (a turn of the head, a breath). No morphing or flicker in the frames inspected.
  - The third clip could not be downloaded afterwards (the connection to Kaggle timed out), so two of three reached the repository.
- **Why they are not in the film:** a shot lasts 6 to 9 seconds. A 1.4-second clip has to be slowed and then held on its last frame for about seven seconds, which reads as a movement that stops dead. It is also 480x832 stretched to 1080x1920, softer than the 720x1280 keyframe. The slow push-in over the still is smoother for the whole length of the shot.
- **Decision:** All shots stay moving stills (`render: still`). The video stage and its fallback remain in the pipeline for a larger GPU. At 57 GPU minutes per 1.4 seconds, animating the whole film at this length would take about 55 hours, against a quota of 30 a week.
- **What changed my mind:** I expected the model to be the limit. The limit was that an hour of a free GPU buys a second and a half.

## E16. Would a voice recorded as a native Amharic speaker be better?

- **Why:** The first listener to the radio cut said the story was nice but the narration did not sound like a native Amharic speaker (DESIGN.md, test 1).
- **Hypothesis:** The words are the author's, so the cause is the voice. `Sulafat` is a general multilingual voice; a voice the provider lists under `am-ET` should sound more native.
- **Change:** voice only. The film's first line, same text and style instruction, recorded with `am-et-tutor-1` (a woman from Addis Ababa) and `am-et-assistant-1` (a man from Wollo), found by querying the voice library for `am-ET`. Both on `gemini-3.8-flash-lite-tts`, because the main model's daily allowance was used up (`runs.jsonl`, stage `narration`, purpose `voice comparison after audience feedback`).
- **Measured:** `am-et-tutor-1` 7.79 s, 0.110 s per character; `am-et-assistant-1` 7.51 s, 0.106; `Sulafat` on the main model 8.00 s, 0.113. The native voices are slightly faster, not enough to matter.
- **Result:** The author, a native speaker, listened to all three (`outputs/narration/voice_test/`) and chose to keep `Sulafat`.
- **Decision:** No change to `narration_voice`. The hypothesis was not confirmed by the one judge who could confirm it. The listener's comment stands in DESIGN.md as given, and the question goes to the remaining listeners.
- **Also learned:** the speech allowance resets at 08:00 UTC. It is a daily limit after all, not the rolling window that E8 concluded from one evening's behaviour.
