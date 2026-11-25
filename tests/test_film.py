"""End-to-end check of the finished film with real FFmpeg and stand-in pictures and voice."""
import copy

import pytest

from pipeline import assemble, music, narration, shots, timing
from pipeline.common import probe_duration
from tests import FIXTURE
from pipeline.validate import load_storyboard
from tests.test_narration import FakeSynth
from tests.test_shots import make_image, video_size


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("film")
    sb = copy.deepcopy(load_storyboard(FIXTURE))
    for shot in sb["shots"]:
        shot["narration"]["lang"] = "en"
        shot["narration"]["text"] = shot["narration"]["source_en"]
    durations = narration.run(
        sb, lang="en", synth=FakeSynth(), out_dir=tmp / "narration", log_path=tmp / "runs.jsonl", sleep=lambda _: None,
    )
    plan = timing.build_timing(sb, durations)
    bed = music.placeholder(plan["total"], out_dir=tmp / "music")
    films = {}
    for aspect, size in (("9:16", "720x1280"), ("16:9", "1280x720")):
        for shot in sb["shots"]:
            make_image(shots.keyframe_path(shot["id"], aspect, tmp / "keyframes"), size)
        clips = shots.render(sb, plan, aspect, keyframes=tmp / "keyframes", videos=tmp / "video", out_dir=tmp / "clips")
        films[aspect] = assemble.film(
            sb, plan, lang="en", aspect=aspect, music=bed, clips=clips,
            narration_dir=tmp / "narration" / "en", out_dir=tmp / "film",
        )
    return plan, films


def test_both_aspect_ratios_are_exported_at_full_size(made):
    _, films = made
    assert video_size(films["9:16"]) == (1080, 1920)
    assert video_size(films["16:9"]) == (1920, 1080)
    assert films["9:16"] != films["16:9"]


def test_film_length_is_the_timeline_including_the_end_card(made):
    plan, films = made
    for path in films.values():
        assert probe_duration(path) == pytest.approx(plan["total"], abs=1 / 24 + 0.03)


def test_film_loudness_and_peak_meet_the_platform_target(made):
    _, films = made
    measured = assemble.measure_loudness(films["9:16"])
    assert float(measured["input_i"]) == pytest.approx(-14.0, abs=1.5)
    assert float(measured["input_tp"]) <= -0.5
