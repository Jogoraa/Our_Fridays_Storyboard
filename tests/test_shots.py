import copy
import subprocess

import pytest

from pipeline import shots, timing
from pipeline.common import probe_duration, run_ffmpeg
from pipeline.validate import load_storyboard


def video_size(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True,
    ).stdout.strip()
    return tuple(int(n) for n in out.split(","))


def make_image(path, size="1280x720", colour="0x8B5A2B"):
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=s={size}:d=1", "-frames:v", "1", str(path)])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("shots")
    sb = copy.deepcopy(load_storyboard())
    sb["shots"] = sb["shots"][:2]
    sb["shots"][0]["camera_move"] = "push_in"
    sb["shots"][1]["camera_move"] = "pan_left"
    plan = timing.build_timing(sb, {"shot_01": 1.0, "shot_02": 1.3})
    for shot in sb["shots"]:
        make_image(shots.keyframe_path(shot["id"], "9:16", tmp / "keyframes"), "720x1280")
        make_image(shots.keyframe_path(shot["id"], "16:9", tmp / "keyframes"), "1280x720")
    return sb, plan, tmp


def render(world, aspect, **kwargs):
    sb, plan, tmp = world
    return shots.render(sb, plan, aspect, keyframes=tmp / "keyframes", videos=tmp / "video", out_dir=tmp / "clips", **kwargs)


def test_still_clip_has_the_timeline_length_and_the_frame_size(world):
    _, plan, _ = world
    clips = render(world, "9:16")
    assert video_size(clips["shot_01"]) == (1080, 1920)
    assert probe_duration(clips["shot_01"]) == pytest.approx(plan["shots"][0]["duration"], abs=0.05)
    assert probe_duration(clips["shot_02"]) == pytest.approx(plan["shots"][1]["duration"], abs=0.05)


def test_landscape_is_rendered_separately(world):
    clips = render(world, "16:9")
    assert video_size(clips["shot_01"]) == (1920, 1080)


def test_second_render_is_a_cache_hit_and_a_new_keyframe_rerenders_only_that_shot(world):
    _, _, tmp = world
    clips = render(world, "9:16")
    before = {k: v.stat().st_mtime_ns for k, v in clips.items()}
    render(world, "9:16")
    assert {k: v.stat().st_mtime_ns for k, v in clips.items()} == before
    make_image(shots.keyframe_path("shot_02", "9:16", tmp / "keyframes"), "736x1280")
    render(world, "9:16")
    after = {k: v.stat().st_mtime_ns for k, v in clips.items()}
    assert after["shot_01"] == before["shot_01"] and after["shot_02"] != before["shot_02"]


def test_video_requested_but_missing_falls_back_to_a_still(world, capsys):
    sb, _, _ = world
    sb["shots"][0]["render"]["9:16"] = "video"
    try:
        clips = render(world, "9:16", only_shot="shot_01")
        assert clips["shot_01"].is_file()
        assert "falling back" in capsys.readouterr().out
    finally:
        sb["shots"][0]["render"]["9:16"] = "still"


def test_generated_video_is_conformed_to_the_shot_length(world):
    sb, plan, tmp = world
    source = shots.video_source_path("shot_02", "9:16", tmp / "video")
    source.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=704x1280:r=24:d=1.5", "-pix_fmt", "yuv420p", str(source)])
    sb["shots"][1]["render"]["9:16"] = "video"
    try:
        clips = render(world, "9:16", only_shot="shot_02")
        assert video_size(clips["shot_02"]) == (1080, 1920)
        assert probe_duration(clips["shot_02"]) == pytest.approx(plan["shots"][1]["duration"], abs=0.05)
    finally:
        sb["shots"][1]["render"]["9:16"] = "still"


def test_missing_keyframe_says_which_one(world):
    sb, plan, tmp = world
    with pytest.raises(FileNotFoundError, match="shot_01"):
        shots.render(sb, plan, "9:16", keyframes=tmp / "nowhere", out_dir=tmp / "clips2")
