# Our Fridays — storyboard starter

A production-ready *plan*, not a completed film or working pipeline.

## What is included

- `storyboard.json`: eight planned shots with English narration, proposed visuals, motion, and story purpose.
- `schema/storyboard.schema.json`: a JSON Schema for this draft contract.
- `DESIGN.md`: an audience-and-testing worksheet, with unknowns clearly marked.

The shot plan totals **84 seconds**, followed by a **4-second “Made with AI” end card**, for a planned **88 seconds**. These timings have not been tested against recorded narration and must be adjusted after the audio is made. The assignment's final film must be 60–90 seconds.

## Direction

The setting and character appearance are suggested, editable creative choices. The characters are fictional, not representations of real people. English narration and English subtitles reflect the current draft. Make and approve character reference images before producing shot keyframes.

Create original instrumental music and lower it under the narration. Time subtitles against the recorded voice, keep them readable, and check safe margins separately in the portrait (9:16) and landscape (16:9) versions. Render both aspect ratios separately; do not assume a central crop will work for every shot. Add phone text and the end card in the editor rather than asking an image model to render them.

## Validate this file

From this directory, with Python and the `jsonschema` package installed:

```bash
python -c 'import json; from jsonschema import Draft202012Validator; s=json.load(open("schema/storyboard.schema.json")); x=json.load(open("storyboard.json")); Draft202012Validator.check_schema(s); Draft202012Validator(s).validate(x); print("Schema valid")'
```

The schema checks structure, but a future pipeline must also verify shot ordering, overall timing, the two aspect ratios, narration fit, subtitle timing and actual rendered outputs.

## Still to do

No images, video clips, narration, music, audience tests, experiments, provider credentials, model-call logs, or working pipeline are included. The next steps are to decide the intended audience and personal significance, generate and test a narration-only radio cut with at least three audience members, and record their actual feedback in DESIGN.md. After the visual rough cut, run the second audience test as described in the assignment. Obtain consent if using a real person's identifiable likeness or voice, and verify licenses for each model and asset.
