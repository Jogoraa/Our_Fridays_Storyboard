import io
import math
import struct
import wave

import pytest

from pipeline.split import SplitError, find_silences, split_take


def take(segments, gaps, rate=24000, amplitude=8000):
    """Build a WAV of tone segments separated by silences. Lengths in seconds."""
    samples = []
    for index, seconds in enumerate(segments):
        samples += [int(amplitude * math.sin(2 * math.pi * 220 * i / rate)) for i in range(int(seconds * rate))]
        if index < len(gaps):
            samples += [0] * int(gaps[index] * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buffer.getvalue()


def seconds_of(data):
    with wave.open(io.BytesIO(data), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def test_find_silences_reports_each_gap():
    silences = find_silences(take([1.0, 1.0, 1.0], [0.8, 1.2]))
    assert len(silences) == 2
    assert silences[0][0] == pytest.approx(1.0, abs=0.05)
    assert silences[0][1] == pytest.approx(1.8, abs=0.05)


def test_split_returns_one_clip_per_line_with_roughly_the_right_lengths():
    clips = split_take(take([2.0, 3.0, 1.5], [1.0, 1.0]), 3)
    assert len(clips) == 3
    assert [seconds_of(c) for c in clips] == pytest.approx([2.0, 3.0, 1.5], abs=0.25)


def test_split_uses_the_longest_gaps_and_keeps_short_pauses_inside_a_line():
    # The 0.3 s pause is a comma inside line two; only the two 1 s gaps separate lines.
    clips = split_take(take([2.0, 1.0, 1.5, 2.0], [1.0, 0.3, 1.0]), 3)
    assert [seconds_of(c) for c in clips] == pytest.approx([2.0, 2.8, 2.0], abs=0.25)


def test_split_trims_leading_and_trailing_silence_but_leaves_a_little_air():
    clips = split_take(take([0.0, 2.0, 0.0], [1.0, 1.0]), 1)
    assert seconds_of(clips[0]) == pytest.approx(2.0, abs=0.25)


def test_split_fails_when_there_are_not_enough_gaps():
    with pytest.raises(SplitError, match="2"):
        split_take(take([2.0, 2.0], [1.0]), 3)


def test_split_fails_when_the_separating_gaps_are_not_clearly_longer_than_the_rest():
    # Three similar pauses but only two lines wanted: no way to know which gap is the boundary.
    with pytest.raises(SplitError, match="ambiguous"):
        split_take(take([2.0, 2.0, 2.0, 2.0], [0.7, 0.72, 0.71]), 2)


# --- when pause lengths alone are ambiguous, the text tells us where the breaks should be ---

def test_weights_pick_the_pause_nearest_where_each_line_should_end():
    # Line one is 2 s, line two is 4 s with a comma pause inside it as long as the line break.
    data = take([2.0, 2.0, 2.0], [0.9, 0.9])
    clips = split_take(data, 2, weights=[20, 40])
    assert [seconds_of(c) for c in clips] == pytest.approx([2.0, 4.9], abs=0.3)
    clips = split_take(data, 2, weights=[40, 20])
    assert [seconds_of(c) for c in clips] == pytest.approx([4.9, 2.0], abs=0.3)


def test_weights_resolve_three_similar_pauses_into_two_lines():
    clips = split_take(take([2.0, 2.0, 2.0, 2.0], [0.7, 0.72, 0.71]), 2, weights=[50, 50])
    assert [seconds_of(c) for c in clips] == pytest.approx([4.7, 4.7], abs=0.3)


def test_weights_must_match_the_number_of_lines():
    with pytest.raises(SplitError, match="weights"):
        split_take(take([2.0, 2.0], [1.0]), 2, weights=[1, 2, 3])


def test_weights_still_fail_when_no_pause_is_near_an_expected_break():
    # One pause, right at the start; the second line break should be near the middle and nothing is there.
    with pytest.raises(SplitError):
        split_take(take([0.5, 9.5], [1.0]), 2, weights=[50, 50])
