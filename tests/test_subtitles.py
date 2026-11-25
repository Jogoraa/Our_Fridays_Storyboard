import re

import pytest

from pipeline.subtitles import build_ass, margin_v, wrap

LINE = "As the bus pulled away, his phone lit up: “Friday. Same time?” Dawit smiled and typed, “I’ll be there.”"


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
    sb["title"] = "Sample Film"
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


def test_radio_cut_subtitles_have_no_extras():
    ass = build_ass(film_storyboard(), timing(), width=1080, height=1920)
    assert not events(ass, "Card")


def test_ass_contains_override_tags_and_no_control_characters():
    ass = build_ass(film_storyboard(), timing(), width=1080, height=1920, extras=True)
    assert not [c for c in ass if ord(c) < 32 and c != "\n"]
    assert r"{\fad(400,0)}" in ass and r"\b1}" in ass and r"\N" in ass


def test_portrait_subtitles_use_shorter_lines_and_larger_type_than_a_40_character_line_allows():
    portrait = build_ass(storyboard(), timing(), width=1080, height=1920)
    landscape = build_ass(storyboard(), timing(), width=1920, height=1080)

    def longest_line(ass):
        return max(len(part) for _, _, text in events(ass, "Sub") for part in text.split(r"\N"))

    def font_size(ass):
        return int(re.search(r"^Style: Sub,[^,]+,(\d+),", ass, re.M).group(1))

    assert longest_line(portrait) <= 30
    assert longest_line(landscape) <= 42
    assert font_size(portrait) >= 52
