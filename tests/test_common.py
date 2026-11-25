import json

import pytest

from pipeline import common
from pipeline.common import (
    ConfigError,
    ProviderError,
    RetryableError,
    cache_key,
    call_with_retry,
    is_cached,
    log_run,
    require_env,
    write_output,
)


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_cache_key_changes_with_payload(tmp_path):
    assert cache_key("s", "1", {"prompt": "a"}) != cache_key("s", "1", {"prompt": "b"})


def test_cache_key_changes_with_stage_version(tmp_path):
    assert cache_key("s", "1", {"prompt": "a"}) != cache_key("s", "2", {"prompt": "a"})


def test_cache_key_changes_when_input_file_changes(tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"one")
    before = cache_key("s", "1", {"prompt": "a"}, [ref])
    ref.write_bytes(b"two")
    assert cache_key("s", "1", {"prompt": "a"}, [ref]) != before


def test_cache_key_stable_for_reordered_dict_and_amharic_text():
    a = cache_key("s", "1", {"text": "ሁልጊዜ አርብ", "voice": "Kore"})
    b = cache_key("s", "1", {"voice": "Kore", "text": "ሁልጊዜ አርብ"})
    assert a == b


def test_is_cached_false_without_meta(tmp_path):
    out = tmp_path / "a.wav"
    out.write_bytes(b"half written")
    assert not is_cached(out, "k")


def test_is_cached_false_for_empty_file(tmp_path):
    out = tmp_path / "a.wav"
    write_output(out, b"", "k", {})
    assert not is_cached(out, "k")


def test_write_output_then_is_cached_true(tmp_path):
    out = tmp_path / "nested" / "a.wav"
    write_output(out, b"data", "k", {"shot": "shot_01"})
    assert is_cached(out, "k")
    assert not is_cached(out, "other-key")
    assert not list(out.parent.glob("*.tmp"))


def test_retry_succeeds_on_third_attempt_logs_three_lines(tmp_path):
    log = tmp_path / "runs.jsonl"
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("429 rate limited")
        return "ok"

    slept = []
    result = call_with_retry(
        fn, stage="narration", provider="gemini", model="m", params={"voice": "Kore"},
        shot="shot_01", sleep=slept.append, log_path=log,
    )
    assert result == "ok"
    lines = read_log(log)
    assert [line["status"] for line in lines] == ["retry", "retry", "ok"]
    assert [line["attempt"] for line in lines] == [1, 2, 3]
    assert slept == [2.0, 4.0]
    assert all(
        {"ts", "stage", "shot", "provider", "model", "params", "seed", "latency_s", "error"} <= line.keys()
        for line in lines
    )


def test_retry_gives_up_after_three_and_raises_provider_error(tmp_path):
    log = tmp_path / "runs.jsonl"

    def fn():
        raise RetryableError("503")

    with pytest.raises(ProviderError, match="503"):
        call_with_retry(fn, stage="s", provider="p", model="m", params={}, sleep=lambda _: None, log_path=log)
    assert [line["status"] for line in read_log(log)] == ["retry", "retry", "failed"]


def test_non_retryable_error_is_not_retried(tmp_path):
    log = tmp_path / "runs.jsonl"
    calls = []

    def fn():
        calls.append(1)
        raise ProviderError("400 bad request")

    with pytest.raises(ProviderError):
        call_with_retry(fn, stage="s", provider="p", model="m", params={}, sleep=lambda _: None, log_path=log)
    assert len(calls) == 1
    assert [line["status"] for line in read_log(log)] == ["failed"]


def test_log_run_masks_key_material(tmp_path):
    log = tmp_path / "runs.jsonl"
    log_run({"stage": "s", "params": {"api_key": "SECRET123", "token": "T0K", "voice": "Kore"}}, path=log)
    text = log.read_text(encoding="utf-8")
    assert "SECRET123" not in text and "T0K" not in text
    assert read_log(log)[0]["params"]["voice"] == "Kore"


def test_log_run_keeps_amharic_readable(tmp_path):
    log = tmp_path / "runs.jsonl"
    log_run({"stage": "s", "params": {"text": "አርብ"}}, path=log)
    assert "አርብ" in log.read_text(encoding="utf-8")


def test_require_env_missing_names_the_variable(monkeypatch):
    monkeypatch.setattr(common, "_env_loaded", True)
    monkeypatch.delenv("NOT_A_REAL_KEY", raising=False)
    with pytest.raises(ConfigError, match="NOT_A_REAL_KEY"):
        require_env("NOT_A_REAL_KEY")


def test_require_env_blank_value_counts_as_missing(monkeypatch):
    monkeypatch.setattr(common, "_env_loaded", True)
    monkeypatch.setenv("BLANK_KEY", "  ")
    with pytest.raises(ConfigError, match="BLANK_KEY"):
        require_env("BLANK_KEY")
