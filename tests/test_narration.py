import copy
import io
import json
import math
import struct
import wave

import pytest

from pipeline import narration
from pipeline.common import ProviderError
from pipeline.validate import load_storyboard


def wav_bytes(seconds=1.0, amplitude=8000, rate=24000):
    frames = int(seconds * rate)
    samples = (int(amplitude * math.sin(2 * math.pi * 220 * i / rate)) for i in range(frames))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    return buffer.getvalue()


class FakeSynth:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or []

    def __call__(self, text, *, model, voice, style_instruction):
        self.calls.append(text)
        if self.responses:
            return self.responses.pop(0)
        return wav_bytes(1.0 + 0.1 * len(self.calls))


@pytest.fixture
def sb():
    """The repo storyboard, normalised to English so tests do not depend on the film's language."""
    board = copy.deepcopy(load_storyboard())
    for shot in board["shots"]:
        shot["narration"]["lang"] = "en"
        shot["narration"]["text"] = shot["narration"]["source_en"]
    return board


@pytest.fixture
def run(tmp_path):
    def _run(sb, synth, **kwargs):
        kwargs.setdefault("lang", "en")
        return narration.run(
            sb, synth=synth, out_dir=tmp_path / "narration", log_path=tmp_path / "runs.jsonl",
            sleep=lambda _: None, **kwargs,
        )
    return _run


def log_lines(tmp_path):
    path = tmp_path / "runs.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_first_run_calls_once_per_shot_and_measures_durations(sb, run, tmp_path):
    synth = FakeSynth()
    durations = run(sb, synth)
    assert len(synth.calls) == 8
    assert set(durations) == {s["id"] for s in sb["shots"]}
    assert durations["shot_01"] == pytest.approx(1.1, abs=0.01)
    assert len(log_lines(tmp_path)) == 8
    assert all(line["stage"] == "narration" and line["status"] == "ok" for line in log_lines(tmp_path))


def test_second_run_makes_no_calls_and_returns_same_durations(sb, run, tmp_path):
    first = run(sb, FakeSynth())
    synth = FakeSynth()
    second = run(sb, synth)
    assert synth.calls == []
    assert second == first
    assert len(log_lines(tmp_path)) == 8


def test_editing_one_line_calls_only_that_shot(sb, run, tmp_path):
    run(sb, FakeSynth())
    sb["shots"][2]["narration"]["text"] = "A changed line for shot three."
    synth = FakeSynth()
    run(sb, synth)
    assert synth.calls == ["A changed line for shot three."]
    assert [line["shot"] for line in log_lines(tmp_path)[8:]] == ["shot_03"]


def test_changing_the_voice_regenerates_every_shot(sb, run):
    run(sb, FakeSynth())
    sb["narration_voice"]["voice"] = "Achernar"
    synth = FakeSynth()
    run(sb, synth)
    assert len(synth.calls) == 8


def test_silent_audio_is_retried_and_not_cached(sb, run, tmp_path):
    silent = wav_bytes(2.0, amplitude=0)
    synth = FakeSynth(responses=[silent])
    run(sb, synth, only_shot="shot_01")
    assert len(synth.calls) == 2
    statuses = [line["status"] for line in log_lines(tmp_path)]
    assert statuses == ["retry", "ok"]


def test_too_short_audio_fails_after_three_attempts_and_leaves_no_cache(sb, run, tmp_path):
    synth = FakeSynth(responses=[wav_bytes(0.1)] * 3)
    with pytest.raises(ProviderError):
        run(sb, synth, only_shot="shot_01")
    assert not (tmp_path / "narration" / "en" / "shot_01.wav").exists()
    retry = FakeSynth()
    run(sb, retry, only_shot="shot_01")
    assert len(retry.calls) == 1


def test_only_shot_limits_calls(sb, run):
    synth = FakeSynth()
    durations = run(sb, synth, only_shot="shot_04")
    assert len(synth.calls) == 1
    assert list(durations) == ["shot_04"]


def test_english_track_uses_source_lines_when_narration_is_amharic(sb, run, tmp_path):
    for shot in sb["shots"]:
        shot["narration"]["text"] = "ሁልጊዜ አርብ"
        shot["narration"]["lang"] = "am"
    synth = FakeSynth()
    run(sb, synth, lang="en", only_shot="shot_01")
    assert synth.calls == [sb["shots"][0]["narration"]["source_en"]]
    assert (tmp_path / "narration" / "en" / "shot_01.wav").exists()


def test_force_regenerates_even_when_cached(sb, run):
    run(sb, FakeSynth(), only_shot="shot_01")
    synth = FakeSynth()
    run(sb, synth, only_shot="shot_01", force=True)
    assert len(synth.calls) == 1


# --- one call for the whole film (the free speech quota is counted per request) ---

from pipeline.common import QuotaError  # noqa: E402
from tests.test_split import take  # noqa: E402


class BatchSynth:
    """Speaks every line in one take, with a clear pause where each separator is."""

    PACE = 0.02  # seconds per character

    def __init__(self, gap=1.0, fail_models=()):
        self.calls = []
        self.gap = gap
        self.fail_models = set(fail_models)

    def __call__(self, text, *, model, voice, style_instruction):
        self.calls.append((model, text))
        if model in self.fail_models:
            raise QuotaError("HTTP 429: limit: 10 requests per day")
        # Like a real voice: each line takes time in proportion to its length.
        lines = text.split(narration.SEPARATOR)
        return take([self.PACE * len(line) for line in lines], [self.gap] * (len(lines) - 1))


def test_batch_records_all_shots_in_one_call(sb, run, tmp_path):
    synth = BatchSynth()
    durations = run(sb, synth, batch=True)
    assert len(synth.calls) == 1
    assert len(durations) == 8
    for shot in sb["shots"]:
        expected = BatchSynth.PACE * len(shot["narration"]["text"])
        assert durations[shot["id"]] == pytest.approx(expected, abs=0.25)
    assert len(list((tmp_path / "narration" / "en" / "takes").glob("*.wav"))) == 1
    lines = log_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["params"]["mode"] == "batch" and len(lines[0]["params"]["shots"]) == 8


def test_after_a_batch_one_edited_line_costs_one_single_shot_call(sb, run, tmp_path):
    run(sb, BatchSynth(), batch=True)
    sb["shots"][2]["narration"]["text"] = "A changed line for shot three."
    synth = FakeSynth()
    run(sb, synth, batch=True)
    assert synth.calls == ["A changed line for shot three."]
    assert log_lines(tmp_path)[-1]["shot"] == "shot_03"


def test_batch_that_cannot_be_split_falls_back_to_one_call_per_shot(sb, run, tmp_path):
    class Unsplittable(BatchSynth):
        def __call__(self, text, **kwargs):
            if narration.SEPARATOR.strip() in text:
                self.calls.append(("batch", text))
                return take([16.0], [])
            return FakeSynth.__call__(self, text, **kwargs)
    synth = Unsplittable()
    synth.responses = []
    durations = run(sb, synth, batch=True)
    assert len(durations) == 8
    statuses = [(line["params"].get("mode", "single"), line["status"]) for line in log_lines(tmp_path)]
    assert statuses[:2] == [("batch", "retry"), ("batch", "failed")]
    assert statuses[2:] == [("single", "ok")] * 8


def test_daily_quota_on_the_main_voice_model_falls_back_to_the_lighter_one(sb, run, tmp_path):
    main, lighter = narration.models()
    synth = BatchSynth(fail_models=[main])
    run(sb, synth, batch=True)
    assert [model for model, _ in synth.calls] == [main, lighter]
    assert [(line["model"], line["status"]) for line in log_lines(tmp_path)] == [(main, "failed"), (lighter, "ok")]


def test_a_split_that_puts_a_sentence_in_the_wrong_shot_is_rejected_by_the_pace_check():
    # Measured on the first real Amharic take: 0.073 and 0.143 s/char against ~0.11 for the rest.
    texts = ["x" * 79, "x" * 82, "x" * 97, "x" * 73, "x" * 58]
    seconds = [9.04, 9.06, 7.06, 10.44, 6.14]
    clips = [wav_bytes(s) for s in seconds]
    with pytest.raises(narration.RetryableError, match="misaligned"):
        narration._check_pace(clips, texts)


def test_natural_variation_in_pace_is_accepted():
    # Measured on the per-shot English takes: 0.075 to 0.098 s/char.
    texts = ["x" * n for n in (98, 95, 107, 95, 82, 98, 103, 104)]
    clips = [wav_bytes(s) for s in (9.48, 8.28, 9.6, 7.2, 6.12, 7.76, 8.0, 10.2)]
    narration._check_pace(clips, texts)


def test_waits_for_quota_when_asked_and_then_finishes(sb, run, tmp_path):
    class Limited(FakeSynth):
        def __call__(self, text, *, model, voice, style_instruction):
            self.calls.append(text)
            if len(self.calls) in (2, 3):  # both voice models refuse once, after the first shot
                raise QuotaError("HTTP 429: limit: 10 requests per day. Please retry in 6m40s", retry_after=400.0)
            return wav_bytes(1.0)

    slept = []
    synth = Limited()
    durations = narration.run(
        sb, lang="en", synth=synth, out_dir=tmp_path / "narration", log_path=tmp_path / "runs.jsonl",
        sleep=slept.append, wait_for_quota=True,
    )
    assert len(durations) == 8
    assert slept == [405.0]


def test_without_waiting_a_quota_error_stops_the_run_but_keeps_finished_shots(sb, run, tmp_path):
    class Limited(FakeSynth):
        def __call__(self, text, *, model, voice, style_instruction):
            self.calls.append(text)
            if len(self.calls) > 2:
                raise QuotaError("HTTP 429: per day", retry_after=400.0)
            return wav_bytes(1.0)

    with pytest.raises(QuotaError):
        run(sb, Limited())
    resumed = FakeSynth()
    run(sb, resumed)
    assert len(resumed.calls) == 6
