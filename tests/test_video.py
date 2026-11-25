import copy
import json

import pytest

from pipeline import shots, video
from pipeline.validate import load_storyboard
from tests import FIXTURE


@pytest.fixture
def sb():
    board = copy.deepcopy(load_storyboard(FIXTURE))
    board["shots"][3]["render"]["9:16"] = "video"
    return board


def fake_gpu(tmp_path, fail=False):
    calls = []

    def runner(manifest):
        calls.append(manifest)
        folder = tmp_path / f"job{len(calls)}"
        folder.mkdir()
        records = []
        for item in manifest["items"]:
            if fail:
                records.append({"file": item["file"], "status": "failed", "error": "CUDA out of memory", "attempts": [1, 2, 3]})
            else:
                (folder / item["file"]).write_bytes(b"mp4")
                records.append({"file": item["file"], "status": "ok", "seconds": 600.0, "frames": 73, "steps": 30})
        (folder / "report.json").write_text(json.dumps({"items": records, "gpu": "Tesla T4", "total_seconds": 900}))
        return folder, {"job_minutes": 30.0, "job": "fake"}

    return runner, calls


def run(sb, runner, tmp_path):
    return video.run(sb, runner=runner, keyframes=tmp_path / "keyframes", videos=tmp_path / "video",
                     log_path=tmp_path / "runs.jsonl")


def keyframe(tmp_path, shot="shot_04", data=b"jpeg-one"):
    path = shots.keyframe_path(shot, "9:16", tmp_path / "keyframes")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_only_shots_marked_video_are_sent_with_motion_prompt_and_keyframe(sb, tmp_path):
    keyframe(tmp_path)
    runner, calls = fake_gpu(tmp_path)
    made = run(sb, runner, tmp_path)
    assert [item["file"] for item in calls[0]["items"]] == ["shot_04_9x16.mp4"]
    assert calls[0]["items"][0]["prompt"] == sb["shots"][3]["motion_prompt"]
    assert calls[0]["items"][0]["image_b64"]
    assert len(made) == 1 and (tmp_path / "video" / "shot_04_9x16.mp4").is_file()


def test_cached_clip_starts_no_job_and_a_new_keyframe_does(sb, tmp_path):
    keyframe(tmp_path)
    run(sb, fake_gpu(tmp_path)[0], tmp_path)
    runner, calls = fake_gpu(tmp_path)
    assert run(sb, runner, tmp_path) == [] and calls == []
    keyframe(tmp_path, data=b"jpeg-two")
    run(sb, runner, tmp_path)
    assert len(calls) == 1


def test_a_failed_clip_is_logged_and_leaves_nothing_behind(sb, tmp_path):
    keyframe(tmp_path)
    assert run(sb, fake_gpu(tmp_path, fail=True)[0], tmp_path) == []
    assert not (tmp_path / "video" / "shot_04_9x16.mp4").exists()
    lines = [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["status"] == "failed" and lines[0]["params"]["failed_attempts"] == 3


def test_a_shot_without_a_keyframe_is_skipped(sb, tmp_path):
    runner, calls = fake_gpu(tmp_path)
    assert run(sb, runner, tmp_path) == [] and calls == []
