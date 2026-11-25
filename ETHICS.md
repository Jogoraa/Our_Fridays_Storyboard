# Ethics — consent, labelling, licences

## Consent

"The Window" has no real person in it. Ato Girma, Ato Kebede and Hana are invented characters, described in `storyboard.json` by generic traits and not modelled on anyone. No photograph of a real person is used as a reference: the character reference images are themselves generated from those text descriptions.

The home for the elderly is fictional and unnamed. The author first suggested a specific real charity home. That was not done: naming or showing a real organisation would imply its real residents and staff, and that needs their recorded consent, which we do not have. Nothing in the prompts, the narration or the film names it.

The narration uses a stock prebuilt Gemini TTS voice (`Sulafat`). No voice was cloned or replicated, and no recording of a real person was supplied to any model.

| Real person shown or voiced | Consent record |
|---|---|
| None | Not applicable |

If this changes (for example a real voice is recorded), the consent record is added here before anything of that person is generated.

Audience testers are recorded in `DESIGN.md` by a short description only, never by name.

## The story's source

The story is an adaptation of a widely circulated parable usually called "The Hospital Window". Its authorship is uncertain; it is often credited to Harry Buschman. The film does not claim the story as original. The narration is newly written in Amharic for this film, the setting and characters are changed, and the credit "adapted from a widely shared story" belongs in the public post.

## Depicting age, illness and blindness

The film shows frail elders and reveals that one of them was blind. The prompts ask for dignity: restrained expressions, ordinary clothes, a plain clean room. Girma's blindness is the source of his generosity in the story, not a defect to be pitied, and the narration uses the respectful plural for both men.

## Labelling

- The film ends with a visible end card reading "Made with AI". It is drawn in code by the assembly stage, so it cannot be dropped by accident.
- The platform's AI-content disclosure is switched on when the film is posted.
- Watermarks and provenance metadata added by the models are left intact. The pipeline does not strip metadata.

## Licences and terms

Listed as each model is actually used.

| Stage | Model | Where it runs | Licence or terms | Notes |
|---|---|---|---|---|
| Narration | `gemini-3.8-flash-tts`, fallback `gemini-3.8-flash-lite-tts` | Gemini API, free tier | Gemini API terms | Free-tier inputs may be used to improve Google's products, so no private data is sent |
| Script draft (first story only) | `gemini-3.5-flash-lite` | Gemini API, free tier | Gemini API terms | Its Amharic was rejected; see FAILURES.md F7 |
| References and keyframes | FLUX.2 klein 4B (`black-forest-labs/FLUX.2-klein-4B`) | Kaggle notebook, Tesla T4 | Apache 2.0 | The 4B model, not the 9B one, which is non-commercial |
| Assembly | FFmpeg 9 | Local | LGPL/GPL | A tool, not a model; deterministic |
| Radio-cut bed | FFmpeg synthesis | Local | Our own output | A placeholder, not the score |

Video (Wan 2.2, Apache 2.0) and music (ACE-Step 1.5, MIT) are added here when they have actually been run.

## Style and private data

Prompts describe qualities (naturalistic, muted cream and green, gentle window light) and name no living artist, photographer or film. No private family details are sent to any endpoint.
