import copy
import json

import pytest

from pipeline import keyframes
from tests import FIXTURE
from pipeline.validate import load_storyboard


@pytest.fixture
def sb():
    return copy.deepcopy(load_storyboard(FIXTURE))


class FakeGpu:
    """Stands in for the Kaggle job: writes a small file for every image asked for."""

    def __init__(self, tmp_path, fail=()):
        self.tmp_path = tmp_path
        self.manifests = []
        self.fail = set(fail)

    def __call__(self, manifest):
        self.manifests.append(manifest)
        folder = self.tmp_path / f"job_{id(self)}_{len(self.manifests)}"
        folder.mkdir()
        records = []
        for item in manifest["items"]:
            if item["file"] in self.fail:
                records.append({"file": item["file"], "status": "failed", "error": "CUDA out of memory", "seconds": 1.0})
                continue
            (folder / item["file"]).write_bytes(b"jpeg:" + item["prompt"].encode("utf-8") + str(item["seed"]).encode())
            records.append({"file": item["file"], "status": "ok", "seconds": 12.5})
        (folder / "report.json").write_text(json.dumps({"items": records, "gpu": "Tesla T4", "total_seconds": 300}))
        return folder, {"job_minutes": 20.0, "job": "fake"}


def run(sb, gpu, tmp_path, **kwargs):
    return keyframes.run(
        sb, runner=gpu, references=tmp_path / "references", keyframes=tmp_path / "keyframes",
        log_path=tmp_path / "runs.jsonl", **kwargs,
    )


def log(tmp_path):
    return [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()]


def test_first_run_makes_references_then_every_keyframe_in_one_job(sb, tmp_path):
    gpu = FakeGpu(tmp_path)
    made = run(sb, gpu, tmp_path)
    assert len(gpu.manifests) == 1
    files = [item["file"] for item in gpu.manifests[0]["items"]]
    assert len(files) == 2 * keyframes.CANDIDATES + 8 * 2
    assert files[:6] == ["rahel_c1.jpg", "rahel_c2.jpg", "rahel_c3.jpg", "bekele_c1.jpg", "bekele_c2.jpg", "bekele_c3.jpg"]
    assert (tmp_path / "keyframes" / "shot_01_9x16.jpg").is_file()
    assert (tmp_path / "keyframes" / "shot_08_16x9.jpg").is_file()
    assert len(made) == 22


def test_every_image_is_logged_with_seed_prompt_and_gpu_seconds(sb, tmp_path):
    run(sb, FakeGpu(tmp_path), tmp_path)
    lines = log(tmp_path)
    images = [line for line in lines if line["model"] == keyframes.MODEL]
    assert len(images) == 22
    assert all(line["seed"] and line["params"]["prompt"] and line["gpu_seconds"] == 12.5 for line in images)
    assert lines[-1]["model"] == "gpu-job" and lines[-1]["latency_s"] == 1200.0


def test_second_run_starts_no_job(sb, tmp_path):
    run(sb, FakeGpu(tmp_path), tmp_path)
    gpu = FakeGpu(tmp_path)
    assert run(sb, gpu, tmp_path) == []
    assert gpu.manifests == []


def test_changing_one_keyframe_prompt_regenerates_only_that_shot(sb, tmp_path):
    run(sb, FakeGpu(tmp_path), tmp_path)
    sb["shots"][2]["keyframe_prompt"] += " A window behind them shows late afternoon light."
    gpu = FakeGpu(tmp_path)
    run(sb, gpu, tmp_path)
    manifest = gpu.manifests[0]
    assert [item["file"] for item in manifest["items"]] == ["shot_03_9x16.jpg", "shot_03_16x9.jpg"]
    # The approved references already exist, so they travel inside the manifest.
    assert set(manifest["embedded"]) == {"rahel_c1.jpg", "bekele_c1.jpg"}


def test_keyframes_use_the_references_of_the_characters_in_the_shot(sb, tmp_path):
    gpu = FakeGpu(tmp_path)
    run(sb, gpu, tmp_path)
    items = {item["file"]: item for item in gpu.manifests[0]["items"]}
    assert items["shot_01_9x16.jpg"]["references"] == ["rahel_c1.jpg", "bekele_c1.jpg"]
    assert items["shot_04_9x16.jpg"]["references"] == ["bekele_c1.jpg"]
    assert sb["style_block"] in items["shot_04_9x16.jpg"]["prompt"]
    # Sent at the size measured to fit the GPUs, not the size asked for.
    assert (items["shot_01_9x16.jpg"]["width"], items["shot_01_9x16.jpg"]["height"]) == (720, 1280)
    assert (items["shot_01_16x9.jpg"]["width"], items["shot_01_16x9.jpg"]["height"]) == (1280, 720)
    assert (items["rahel_c1.jpg"]["width"], items["rahel_c1.jpg"]["height"]) == (864, 1152)
    assert "on the left of the reference image" in items["shot_01_9x16.jpg"]["prompt"]
    assert "on the right of the reference image" in items["shot_01_9x16.jpg"]["prompt"]
    assert "from reference image 1" in items["shot_04_9x16.jpg"]["prompt"]


def test_choosing_a_different_reference_regenerates_that_characters_shots_only(sb, tmp_path):
    run(sb, FakeGpu(tmp_path), tmp_path)
    sb["characters"][0]["reference_asset"] = "outputs/references/rahel_c2.jpg"
    gpu = FakeGpu(tmp_path)
    run(sb, gpu, tmp_path)
    shots_redone = {item["file"][:7] for item in gpu.manifests[0]["items"]}
    with_rahel = {shot["id"] for shot in sb["shots"] if "rahel" in shot["characters"]}
    assert shots_redone == with_rahel


def test_a_failed_image_is_logged_not_cached_and_retried_next_run(sb, tmp_path):
    run(sb, FakeGpu(tmp_path, fail=["shot_05_16x9.jpg"]), tmp_path)
    assert not (tmp_path / "keyframes" / "shot_05_16x9.jpg").exists()
    failed = [line for line in log(tmp_path) if line["status"] == "failed"]
    assert len(failed) == 1 and "out of memory" in failed[0]["error"]
    gpu = FakeGpu(tmp_path)
    run(sb, gpu, tmp_path)
    assert [item["file"] for item in gpu.manifests[0]["items"]] == ["shot_05_16x9.jpg"]


def test_only_shot_limits_the_job(sb, tmp_path):
    run(sb, FakeGpu(tmp_path), tmp_path)
    gpu = FakeGpu(tmp_path)
    run(sb, gpu, tmp_path, only_shot="shot_02", force=True)
    assert [item["file"] for item in gpu.manifests[0]["items"]] == ["shot_02_9x16.jpg", "shot_02_16x9.jpg"]
