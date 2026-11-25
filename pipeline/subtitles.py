"""English subtitles timed against the measured narration, as an ASS file for FFmpeg to burn in."""
from __future__ import annotations

import re

MAX_CHARS = 40
MAX_LINES = 2
HOLD_AFTER = 0.3


def _lines(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrap(text: str, max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES) -> list[str]:
    """Split a narration line into cues of at most two 40-character lines, breaking at sentences."""
    sentences = [s for s in re.split(r"(?<=[.!?…”\"])\s+", text.strip()) if s]
    cues: list[str] = []
    pending = ""
    for sentence in sentences:
        candidate = f"{pending} {sentence}".strip()
        if len(_lines(candidate, max_chars)) <= max_lines:
            pending = candidate
            continue
        if pending:
            cues.append("\n".join(_lines(pending, max_chars)))
        lines = _lines(sentence, max_chars)
        while len(lines) > max_lines:
            cues.append("\n".join(lines[:max_lines]))
            lines = lines[max_lines:]
        pending = " ".join(lines)
    if pending:
        cues.append("\n".join(_lines(pending, max_chars)))
    return cues


def margin_v(width: int, height: int) -> int:
    """Bottom margin: bigger in portrait, where platform buttons cover the lower part of the frame."""
    return round(height * (0.18 if height > width else 0.10))


def _stamp(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    hours, rest = divmod(centis, 360000)
    minutes, rest = divmod(rest, 6000)
    return f"{hours}:{minutes:02d}:{rest // 100:02d}.{rest % 100:02d}"


_STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding"
)
# ASS colours are &HAABBGGRR. BorderStyle 3 draws an opaque box in the outline colour: a message bubble.
_BUBBLES = {
    # role: (box colour, italic, alignment: 7 top-left, 9 top-right)
    "received": ("&H003A3A3A", 0, 7),
    "sent": ("&H00D9822B", 0, 9),
    "draft": ("&H00707070", 1, 9),
}


def _extras(sb: dict, timing: dict, width: int, height: int, font_size: int, margin_h: int) -> tuple[list[str], list[str]]:
    """Styles and events for the phone messages and the end card. All on-screen text is drawn here."""
    top = round(height * (0.14 if height > width else 0.10))
    bubble_size = round(font_size * 1.05)
    styles = [
        f"Style: {role.capitalize()},Arial,{bubble_size},&H00FFFFFF,&H00FFFFFF,{colour},{colour},"
        f"0,{italic},0,0,100,100,0,0,3,{round(bubble_size * 0.45)},0,{align},{margin_h},{margin_h},{top},1"
        for role, (colour, italic, align) in _BUBBLES.items()
    ]
    card_size = round(min(width, height) * 0.055)
    styles.append(
        f"Style: Card,Arial,{card_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        f"0,0,0,0,100,100,2,0,1,0,0,5,{margin_h},{margin_h},0,1"
    )

    events: list[str] = []
    slots = {slot["id"]: slot for slot in timing["shots"]}
    for shot in sb["shots"]:
        slot = slots[shot["id"]]
        shot_end = slot["start"] + slot["duration"]
        for index, message in enumerate(shot.get("overlay_text", [])):
            start = slot["start"] + message["at_fraction"] * slot["duration"]
            drop = top + index * round(bubble_size * 2.6)  # later messages sit below earlier ones
            text = message["text"] + ("|" if message["role"] == "draft" else "")
            events.append(
                f"Dialogue: 1,{_stamp(start)},{_stamp(shot_end)},{message['role'].capitalize()},,0,0,{drop},,"
                f"{{\\fad(250,200)}}{text}"
            )
    card = timing["end_card"]
    title = sb.get("title", "")
    lines = ([f"{{\\fs{round(card_size * 1.5)}\\b1}}{title}{{\\b0\\fs{card_size}}}", ""] if title else []) + [sb["end_card"]["text"]]
    events.append(
        f"Dialogue: 2,{_stamp(card['start'])},{_stamp(card['start'] + card['duration'])},Card,,0,0,0,,"
        f"{{\\fad(400,0)}}" + r"\N".join(lines)
    )
    return styles, events


def build_ass(sb: dict, timing: dict, *, width: int, height: int, extras: bool = False) -> str:
    """Subtitles for the whole film. With extras, also the phone messages and the end card."""
    margin_h = round(width * 0.075)
    font_size = min(round((width - 2 * margin_h) / 21), round(height * 0.052))
    styles = [
        f"Style: Sub,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,"
        f"1,0,0,0,100,100,0,0,1,{max(2, round(font_size / 16))},1,2,{margin_h},{margin_h},{margin_v(width, height)},1",
    ]
    by_id = {shot["id"]: shot for shot in sb["shots"]}
    events: list[str] = []
    for slot in timing["shots"]:
        cues = wrap(by_id[slot["id"]]["narration"]["subtitle_en"])
        start = slot["narration_start"]
        window_end = min(start + slot["narration_duration"] + HOLD_AFTER, slot["start"] + slot["duration"])
        weights = [len(cue) for cue in cues]
        cursor = start
        for index, (cue, weight) in enumerate(zip(cues, weights)):
            last = index == len(cues) - 1
            end = window_end if last else cursor + slot["narration_duration"] * weight / sum(weights)
            text = cue.replace("\n", r"\N")
            events.append(f"Dialogue: 0,{_stamp(cursor)},{_stamp(end)},Sub,,0,0,0,,{text}")
            cursor = end
    if extras:
        more_styles, more_events = _extras(sb, timing, width, height, font_size, margin_h)
        styles += more_styles
        events += more_events
    header = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", _STYLE_FORMAT, *styles, "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])
    return header + "\n" + "\n".join(events) + "\n"
