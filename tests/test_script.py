import copy
import json

import pytest

from pipeline import script
from pipeline.common import ProviderError, RetryableError
from tests import FIXTURE
from pipeline.validate import load_storyboard


@pytest.fixture
def sb():
    return copy.deepcopy(load_storyboard(FIXTURE))


def run(sb, generate, tmp_path, **kwargs):
    return script.run(
        sb, generate=generate, out_dir=tmp_path / "script", log_path=tmp_path / "runs.jsonl",
        sleep=lambda _: None, **kwargs,
    )


def log(tmp_path):
    return [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()]


def test_proposal_lists_every_shot_and_storyboard_is_untouched(sb, tmp_path):
    before = copy.deepcopy(sb)
    proposal = run(sb, lambda text, **_: "አማርኛ መስመር", tmp_path)
    text = proposal.read_text(encoding="utf-8")
    assert all(shot["id"] in text for shot in sb["shots"])
    assert "አማርኛ መስመር" in text
    assert sb == before


def test_second_run_makes_no_calls(sb, tmp_path):
    run(sb, lambda text, **_: "አማርኛ", tmp_path)
    calls = []
    run(sb, lambda text, **_: calls.append(text) or "x", tmp_path)
    assert calls == []


def test_overloaded_model_falls_back_to_the_lighter_one(sb, tmp_path):
    models = script.models()
    assert len(models) == 2 and models[0] != models[1]

    def generate(text, *, model, **_):
        if model == models[0]:
            raise RetryableError("HTTP 503: high demand")
        return "አማርኛ"

    run(sb, generate, tmp_path)
    first_shot = [line for line in log(tmp_path) if line["shot"] == "shot_01"]
    assert [(line["model"], line["status"]) for line in first_shot] == [
        (models[0], "retry"), (models[0], "retry"), (models[0], "failed"), (models[1], "ok"),
    ]
    record = json.loads((tmp_path / "script" / "shot_01.am.json").read_text(encoding="utf-8"))
    assert record["model"] == models[1]


def test_fails_when_every_model_is_down(sb, tmp_path):
    def generate(text, **_):
        raise RetryableError("HTTP 503")

    with pytest.raises(ProviderError):
        run(sb, generate, tmp_path)
