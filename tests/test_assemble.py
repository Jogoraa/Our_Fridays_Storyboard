"""End-to-end check of the radio cut with real FFmpeg and fake narration (no model calls)."""
import copy

import pytest

from pipeline import assemble, music, narration, timing
from pipeline.common import probe_duration
from tests import FIXTURE
from pipeline.validate import load_storyboard
from tests.test_narration import FakeSynth


@pytest.fixture(scope="module")
def cut(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("radio")
    sb = copy.deepcopy(load_storyboard(FIXTURE))
    durations = narration.run(
        sb, lang="en", synth=FakeSynth(), out_dir=tmp / "narration", log_path=tmp / "runs.jsonl", sleep=lambda _: None,
    )
    plan = timing.build_timing(sb, durations)
    bed = music.placeholder(plan["total"], out_dir=tmp / "music")
    kwargs = dict(lang="en", music=bed, narration_dir=tmp / "narration" / "en", out_dir=tmp / "film")
    output = assemble.radio_cut(sb, plan, **kwargs)
    return sb, plan, output, kwargs


def test_radio_cut_length_matches_timing_within_a_frame(cut):
    _, plan, output, _ = cut
    assert probe_duration(output) == pytest.approx(plan["total"], abs=1 / 24 + 0.03)


def test_radio_cut_is_normalised_near_minus_14_lufs(cut):
    _, _, output, _ = cut
    measured = assemble.measure_loudness(output)
    assert float(measured["input_i"]) == pytest.approx(-14.0, abs=1.5)
    assert float(measured["input_tp"]) <= 0.0


def test_second_assembly_is_a_cache_hit(cut):
    sb, plan, output, kwargs = cut
    before = output.stat().st_mtime_ns
    assert assemble.radio_cut(sb, plan, **kwargs) == output
    assert output.stat().st_mtime_ns == before


def test_changed_subtitle_reassembles(cut):
    sb, plan, output, kwargs = cut
    before = output.stat().st_mtime_ns
    changed = copy.deepcopy(sb)
    changed["shots"][0]["narration"]["subtitle_en"] = "A different subtitle."
    assemble.radio_cut(changed, plan, **kwargs)
    assert output.stat().st_mtime_ns != before


def test_mix_applies_the_tempo_to_every_narration_clip(cut):
    _, plan, _, _ = cut
    count = len(plan["shots"])
    faster = {**plan, "tempo": 1.08}
    assert assemble.mix_filter(faster, count).count("atempo=1.08") == count
    assert "atempo" not in assemble.mix_filter({**plan, "tempo": 1.0}, count)
