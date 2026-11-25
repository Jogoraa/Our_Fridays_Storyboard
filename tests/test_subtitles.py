import re

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
