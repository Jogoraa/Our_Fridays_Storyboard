import pytest

from pipeline.timing import FPS, TimingError, build_timing, check_total


def storyboard(n=8, end_card=3):
    return {
        "shots": [{"id": f"shot_{i:02d}"} for i in range(1, n + 1)],
        "end_card": {"duration_seconds": end_card, "text": "Made with AI"},
    }


def durations(seconds, n=8):
    return {f"shot_{i:02d}": seconds for i in range(1, n + 1)}


def test_shots_are_contiguous_and_frame_aligned():
    timing = build_timing(storyboard(), durations(7.013))
    cursor = 0.0
    for shot in timing["shots"]:
        assert shot["start"] == pytest.approx(cursor, abs=1e-6)
        frames = shot["duration"] * FPS
        assert frames == pytest.approx(round(frames), abs=1e-6)
        cursor += shot["duration"]
    assert timing["end_card"]["start"] == pytest.approx(cursor, abs=1e-6)


def test_shot_is_long_enough_for_lead_narration_and_tail():
    timing = build_timing(storyboard(), durations(7.013), lead=0.4, tail=0.7)
    shot = timing["shots"][0]
    assert shot["duration"] >= 0.4 + 7.013 + 0.7
    assert shot["duration"] < 0.4 + 7.013 + 0.7 + 1 / FPS


def test_narration_starts_after_lead():
    timing = build_timing(storyboard(), durations(7.0), lead=0.4)
    second = timing["shots"][1]
    assert second["narration_start"] == pytest.approx(second["start"] + 0.4)
    assert second["narration_duration"] == 7.0


def test_total_includes_end_card():
    timing = build_timing(storyboard(end_card=3), durations(7.0))
    assert timing["total"] == pytest.approx(sum(s["duration"] for s in timing["shots"]) + 3)
    assert timing["end_card"]["duration"] == 3


def test_missing_duration_for_a_shot_raises():
    partial = durations(7.0)
    del partial["shot_05"]
    with pytest.raises(TimingError, match="shot_05"):
        build_timing(storyboard(), partial)


def test_total_inside_limits_passes():
    check_total(build_timing(storyboard(), durations(7.0)))


def test_overrun_raises_with_per_shot_breakdown():
    timing = build_timing(storyboard(), durations(11.0))
    with pytest.raises(TimingError) as info:
        check_total(timing)
    message = str(info.value)
    assert "over" in message and "shot_01" in message and "shot_08" in message
    assert f"{timing['total'] - 90:.1f}" in message


def test_underrun_raises():
    with pytest.raises(TimingError, match="under"):
        check_total(build_timing(storyboard(), durations(4.0)))
