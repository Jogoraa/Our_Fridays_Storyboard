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
    return copy.deepcopy(load_storyboard())


@pytest.fixture
def run(tmp_path):
    def _run(sb, synth, **kwargs):
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
