import copy

import pytest

from tests import FIXTURE
from pipeline.validate import StoryboardError, load_storyboard, validate_storyboard


@pytest.fixture
def sb():
    return copy.deepcopy(load_storyboard(FIXTURE))


def test_repo_storyboard_is_valid(sb):
    assert len(sb["shots"]) == 8
    assert sb["schema_version"] == "1.1"


def test_unknown_character_rejected(sb):
    sb["shots"][0]["characters"] = ["nobody"]
    with pytest.raises(StoryboardError, match="nobody"):
        validate_storyboard(sb)


def test_duplicate_shot_ids_rejected(sb):
    sb["shots"][1]["id"] = sb["shots"][0]["id"]
    with pytest.raises(StoryboardError, match="shot_01"):
        validate_storyboard(sb)


def test_unordered_shot_ids_rejected(sb):
    sb["shots"][0], sb["shots"][1] = sb["shots"][1], sb["shots"][0]
    with pytest.raises(StoryboardError, match="order"):
        validate_storyboard(sb)


def test_missing_reason_rejected(sb):
    del sb["shots"][2]["reason"]
    with pytest.raises(StoryboardError, match="reason"):
        validate_storyboard(sb)


def test_planned_total_outside_60_90_rejected(sb):
    sb["shots"][0]["duration_seconds"] = 60
    with pytest.raises(StoryboardError, match="60"):
        validate_storyboard(sb)


def test_every_shot_renders_both_aspect_ratios(sb):
    del sb["shots"][0]["render"]["9:16"]
    with pytest.raises(StoryboardError, match="9:16"):
        validate_storyboard(sb)


def test_the_films_own_storyboard_is_valid():
    live = load_storyboard()
    assert 8 <= len(live["shots"]) <= 12
    assert all(shot["reason"] for shot in live["shots"])
