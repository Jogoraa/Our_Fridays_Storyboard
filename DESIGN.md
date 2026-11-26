# Design — The Window

Audience, intent and the reason for every shot were written before any picture was generated. The git history shows the order.

## The story

Two old men share a room in a home for the elderly. Ato Girma's bed is beside the room's only window. Ato Kebede must lie flat and sees only the ceiling. Every afternoon Girma sits up and describes what he sees outside: a garden, children chasing a ball, sweethearts walking, hills beyond the city. Kebede closes his eyes and sees it all, and it keeps him going for weeks. One morning Girma's bed is empty. Kebede asks to be moved to the window, looks out, and finds only a white wall. The caregiver tells him Girma was blind. He had invented it all to give his friend the hope to go on living.

It is an adaptation of a widely circulated parable usually called "The Hospital Window" (author uncertain; often credited to Harry Buschman). The author of this project brought it in its Amharic form. The setting (a home for the elderly in Addis Ababa instead of a hospital), the characters, the things Girma describes and the narration are this project's own. All characters and the home are fictional.

## Audience

Young Ethiopian adults: the author's friends and cohort colleagues, people who grew up around elders. They watch on a phone, vertically, often somewhere noisy, which is why the English subtitles are burned in.

## Intent

At the end the viewer should feel how much a small, invented kindness can carry, and want to give someone hope. The film should end on gratitude, not on despair: the last image is Kebede in tears but smiling.

## Language

Narration in Amharic, the audience's first language, using the respectful plural for the elders. English subtitles. The Amharic is written and approved by the author, a native speaker.

## Why each shot exists

| Shot | What we see | Why it is in the film |
|---|---|---|
| 01 | The room: two beds, one window | Establish the place, the two men and the one window everything turns on |
| 02 | Kebede flat on his back, staring up; Girma's shawl by the window behind him | Show why Kebede depends on Girma: he can only see the ceiling |
| 03 | Girma facing the window light, describing | Introduce the daily ritual |
| 04 | The imagined garden, children with a ball | Let the audience see the world as vividly as Kebede imagines it |
| 05 | The imagined couple, city and hills | Widen that world, so the wall later feels like a real loss |
| 06 | Kebede, eyes closed, smiling | Show what the stories give him |
| 07 | The empty bed, the caregiver's bowed head | The loss |
| 08 | Kebede straining up toward the window | His hope: at last he will see it himself |
| 09 | A blank white wall | The turn: there was never anything to see |
| 10 | The caregiver's hand on his shoulder | The reveal, told gently by someone who knew Girma |
| 11 | Kebede in tears, smiling, in warm light | The meaning, and an ending on gratitude |

The same reasons are stored per shot in `storyboard.json` as `reason`, and validation fails if one is missing.

Two look decisions follow from the intent. The imagined shots (04, 05) have their own warmer, more luminous style so that they feel better than the real room. The white wall (09) is flat and grey and the only static shot, and the music nearly stops there.

## Decision log

### 25 November: the story changed before any picture was made

The project began as "Our Fridays", a fictional story about two friends and an unspoken love. The pipeline was built around it and a radio cut was produced in English and in Amharic (its storyboard and measurements are kept in `outputs/archive/our_fridays/`; the calls are in `runs.jsonl`).

Before it was shown to anyone, the author chose to replace the story with this one. His reasons, as he gave them on 26 November:

> "I've known the story a long ago. My friend sent me the story on Telegram and it touched my heart: that giving a hope for each other is the best thing we could do, and how hope gives us a bright imagination, and some things are even better on listening level, and they are not as good as when we hear them from the other perspective. And thirdly, hope is the most important thing to keep people alive and in health as well."

Three things follow from that for the film. Hope given in words is the whole plot, so the narration carries the story and the pictures serve it. What is heard is better than what is seen, so the imagined garden (shots 04 and 05) is the most beautiful thing in the film and the real view (shot 09) is a blank wall. And hope keeps a person alive, so the film ends on Kebede grateful, not broken.

What the builder observed at the time: the brief asks for a story that matters to the maker and their family, and "Our Fridays" was invented for the assignment; this parable is one the author already carried, in his own language, about elders.

What the change cost: the narration, the subtitles and the radio cut. What it did not cost: any code. The storyboard is the only file that changed, which is the point of having one contract. The tests were moved onto a frozen sample storyboard at the same time so they no longer depend on which film is being made.

One request was not followed as stated. The author suggested setting the film in a specific, real charity home for the elderly. The home in the film is unnamed and fictional instead, because showing or naming a real organisation and its residents would need their recorded consent (see ETHICS.md).

## Test 1: the radio cut

Narration over placeholder music on a black screen with subtitles (`uv run film --radio-cut`), played to at least three people from the audience.

Questions to ask: What happened in the story, in your own words? Where did you lose interest or get confused? Did you see the ending coming, and how did it leave you feeling? Did any word sound wrong or disrespectful toward the elders?

**Three listeners:** the same three friends who later watched the film (colleagues from the author's workplace and a friend from school), as the author reports it. Two of them commented on the radio cut by itself.

| Listener | When | What they said |
|---|---|---|
| A friend of the author | 25 to 26 November, after hearing the radio cut | "It's quite a nice story," but the narration does not sound like a native Amharic speaker. |
| A second friend of the author | 25 to 26 November, after hearing the radio cut | Some Amharic words need a particular pronunciation and the AI narrator does not fully get them, which is "a bit funny, not in a bad way though". |
| The third friend | 25 to 26 November | No separate comment on the radio cut alone was reported. |

Two listeners, independently, heard the same thing: the story works and the voice is not quite a native one. The second was more specific than the first: it is particular words, and the effect is slightly comic.

What changed because of it:

- The complaint was about the voice, not the words (the Amharic text was written by the author, a native speaker). The narrator was `Sulafat`, a general multilingual voice. Looking for the cause turned up two voices in the provider's library that are recorded as native Amharic speakers and had not been tried: `am-et-tutor-1` (a woman in her early fifties from Addis Ababa) and `am-et-assistant-1` (a man in his late twenties from Wollo).
- The film's first line was recorded with each (`outputs/narration/voice_test/`) and the author, a native speaker, compared all three. He chose to keep `Sulafat`. So this comment led to an experiment (EXPERIMENTS E16) and a considered decision, not to a change in the storyboard. It is recorded here as it happened.
- The second comment named the fault more exactly, and the author gave an example: ይጋሩ in the first line is read pressed, as if the consonant were doubled. The first line was recorded three more ways (a softer reading instruction, a different word, both). The author judged none of them better than the current take, so the narration stays (EXPERIMENTS E17). Two remedies tried, neither adopted: the non-native quality is a limit of the free speech model for Amharic, and the film says so in its documents instead of hiding it.

## Test 2: the near-final cut

The near-final film, played to at least three people from the audience.

Questions to ask: Are Girma and Kebede recognisably the same two men in every shot? Could you read the subtitles comfortably? Was the music ever in the way of the voice? Did the white wall and the reveal land?

**Three viewers.** They saw the first cut with pictures, before shot 2 was corrected.

| Viewers | When | What they said |
|---|---|---|
| Three friends of the author: colleagues from his workplace and a friend from school | 25 November | They asked how Gash Girma could be in two places at once, "lying on the bed and sitting behind": was it meant to be something abstract, or a mistake that needed fixing? |

What changed because of it:

- It was a mistake, and the viewers had seen exactly what the builder had seen on the contact sheet: in the vertical version of shot 2 there were three men, one lying down and two sitting behind him. The viewers read the extra figure as the same man twice, which is worse than an extra stranger: it made them wonder whether the film was being symbolic at the moment it most needed to be plain.
- Shot 2 was changed in the storyboard. Its `characters` went from two to one, and its `keyframe_prompt` and `reason` were rewritten: Kebede alone, flat on his back, with the window and Girma's folded shawl out of focus behind him. Only shot 2 was regenerated, re-rendered and cut back into both films (EXPERIMENTS E14; `git log -- storyboard.json`).
- A first attempt, adding the sentence "exactly two people in the picture" to the prompt, did not fix it. The rejected images are kept in `outputs/keyframes/rejected/`.

### What the same people said after seeing both

The three friends heard the radio cut first and saw the film with pictures afterwards. Comparing the two, they told the author the story "makes a lot more sense this way", with the pictures.

The friend who first sent the author this story on Telegram also watched the film. He was amazed and said: "it feels alive now."

What this means for the design. The radio cut did its job as a cheap prototype: it showed that the words carried the story and it surfaced the pronunciation problem before any picture existed. But for this particular story it could only ever be half a test. The story is about what one man sees and another imagines, and the turn is a picture, a white wall. Listeners followed it on the voice alone; they felt it when they could see the garden and then see the wall. That is the author's second reason for choosing the story, turned around: some things are better heard than seen, and this ending is the one thing that has to be seen.

Not yet asked of these viewers, and worth asking now that shot 2 is fixed: can the subtitles be read comfortably, and is the music ever in the way.
