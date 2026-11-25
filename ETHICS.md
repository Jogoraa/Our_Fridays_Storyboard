# Ethics — consent, labelling, licences

## Consent

"Our Fridays" is fiction. Rahel and Bekele are invented characters, described in `storyboard.json` by generic traits, not modelled on any real person. No photograph of a real person is used as a reference image.

The narration uses a stock prebuilt Gemini TTS voice (`Sulafat`). No voice was cloned or replicated, and no recording of a real person was supplied to any model.

| Real person shown or voiced | Consent record |
|---|---|
| None | Not applicable |

If this changes (for example a real voice is recorded), the consent record is added here before anything of that person is generated.

Audience testers are recorded in `DESIGN.md` by a short description only, never by name.

## Labelling

- The film ends with a visible end card reading "Made with AI". It is drawn in code by the assembly stage, so it cannot be dropped by accident.
- The platform's AI-content disclosure is switched on when the film is posted.
- Watermarks and provenance metadata added by the models (for example SynthID) are left intact. The pipeline does not strip metadata.

## Licences and terms

Filled in as each model is actually used. Models not yet used are not listed.

| Stage | Model | Where it runs | Licence or terms | Notes |
|---|---|---|---|---|
| Narration | `gemini-3.8-flash-tts` | Gemini API, free tier | Gemini API terms | Free-tier inputs may be used to improve Google's products, so no private data is sent |
| Script draft | `gemini-3.8-flash` | Gemini API, free tier | Gemini API terms | Same note |
| Assembly | FFmpeg 9 | Local | LGPL/GPL | A tool, not a model; deterministic |
| Radio-cut bed | FFmpeg synthesis | Local | Our own output | A placeholder, not the score |

## Style and private data

Prompts describe qualities (naturalistic, warm, muted terracotta and navy) and name no living artist, photographer or film. No private family details are sent to any endpoint; the story is invented.
