import re

import pytest

from pipeline.subtitles import build_ass, margin_v, wrap

LINE = "As the bus pulled away, his phone lit up: “Friday. Same time?” Bekele smiled and typed, “I’ll be there.”"


def test_wrap_never_exceeds_two_lines_of_40():
    for cue in wrap(LINE):
        lines = cue.split("\n")
        assert len(lines) <= 2
        assert all(len(line) <= 40 for line in lines)


def test_wrap_keeps_all_words_in_order():
    assert " ".join(" ".join(wrap(LINE)).split()) == LINE


def test_short_text_is_one_cue():
    assert wrap("He was proud.") == ["He was proud."]


def timing():
    return {
        "fps": 24,
        "shots": [
            {"id": "shot_01", "start": 0.0, "duration": 8.0, "narration_start": 0.4, "narration_duration": 6.9},
            {"id": "shot_02", "start": 8.0, "duration": 8.0, "narration_start": 8.4, "narration_duration": 6.9},
        ],
        "end_card": {"start": 16.0, "duration": 3.0},
        "total": 19.0,
    }


def storyboard():
    return {"shots": [
        {"id": "shot_01", "narration": {"subtitle_en": LINE}},
        {"id": "shot_02", "narration": {"subtitle_en": "He was proud."}},
    ]}


def cue_times(ass):
    def seconds(stamp):
        h, m, s = stamp.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return [
        (seconds(m.group(1)), seconds(m.group(2)))
        for m in re.finditer(r"^Dialogue: 0,([\d:.]+),([\d:.]+),", ass, re.M)
    ]


def test_build_ass_cues_stay_inside_narration_window_and_do_not_overlap():
    times = cue_times(build_ass(storyboard(), timing(), width=1080, height=1920))
    assert len(times) >= 3
    first_shot = [t for t in times if t[1] <= 8.0]
    assert first_shot[0][0] >= 0.4 - 0.011
    assert first_shot[-1][1] <= 0.4 + 6.9 + 0.35
    for (_, end), (start, _) in zip(times, times[1:]):
        assert start >= end - 0.011


def test_build_ass_declares_the_frame_size():
    ass = build_ass(storyboard(), timing(), width=1080, height=1920)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass


def test_portrait_margin_larger_than_landscape():
    assert margin_v(1080, 1920) > margin_v(1920, 1080)
    assert margin_v(1080, 1920) == round(1920 * 0.18)
    assert margin_v(1920, 1080) == round(1080 * 0.10)


# --- text that is drawn in the edit, never generated inside an image ---

def film_storyboard():
    sb = storyboard()
    sb["end_card"] = {"duration_seconds": 3, "text": "Made with AI"}
    sb["title"] = "Our Fridays"
    sb["shots"][1]["overlay_text"] = [
        {"text": "አርብ። ልክ እንደ ተለመደው?", "at_fraction": 0.25, "role": "received"},
        {"text": "እመጣለሁ", "at_fraction": 0.75, "role": "sent"},
    ]
    return sb


def events(ass, style):
    def seconds(stamp):
        h, m, s = stamp.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    pattern = rf"^Dialogue: \d+,([\d:.]+),([\d:.]+),{style},[^\n]*?,,(.*)$"
    return [(seconds(m.group(1)), seconds(m.group(2)), m.group(3)) for m in re.finditer(pattern, ass, re.M)]


def test_end_card_text_is_on_screen_for_the_whole_end_card():
    ass = build_ass(film_storyboard(), timing(), width=1080, height=1920, extras=True)
    cards = events(ass, "Card")
    assert any("Made with AI" in text for _, _, text in cards)
    start, end, _ = next(c for c in cards if "Made with AI" in c[2])
    assert start == pytest.approx(16.0, abs=0.02) and end == pytest.approx(19.0, abs=0.02)


def test_phone_messages_appear_inside_their_shot_in_order():
    ass = build_ass(film_storyboard(), timing(), width=1080, height=1920, extras=True)
    received, sent = events(ass, "Received"), events(ass, "Sent")
    assert len(received) == 1 and len(sent) == 1
    assert received[0][0] == pytest.approx(8.0 + 0.25 * 8.0, abs=0.02)
    assert sent[0][0] == pytest.approx(8.0 + 0.75 * 8.0, abs=0.02)
    assert received[0][1] <= 16.0 and sent[0][1] <= 16.0
    assert "እመጣለሁ" in sent[0][2]


def test_radio_cut_subtitles_have_no_extras():
    ass = build_ass(film_storyboard(), timing(), width=1080, height=1920)
    assert not events(ass, "Card") and not events(ass, "Sent")


def test_ass_contains_override_tags_and_no_control_characters():
    ass = build_ass(film_storyboard(), timing(), width=1080, height=1920, extras=True)
    assert not [c for c in ass if ord(c) < 32 and c != "\n"]
    assert r"{\fad(250,200)}" in ass and r"\b1}" in ass and r"\N" in ass
