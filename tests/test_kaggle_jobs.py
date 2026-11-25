import pytest

from pipeline import kaggle_jobs
from pipeline.common import ProviderError


def test_wait_survives_a_few_dropped_polls(monkeypatch):
    answers = iter([ProviderError("connection reset"), "running", ProviderError("connection reset"), "complete"])

    def status(ref):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(kaggle_jobs, "status", status)
    assert kaggle_jobs.wait("user/job", sleep=lambda _: None) >= 0


def test_wait_gives_up_when_contact_is_lost_for_good(monkeypatch):
    def status(ref):
        raise ProviderError("connection reset")

    monkeypatch.setattr(kaggle_jobs, "status", status)
    with pytest.raises(ProviderError, match="lost contact"):
        kaggle_jobs.wait("user/job", sleep=lambda _: None)


def test_wait_reports_a_failed_job(monkeypatch):
    monkeypatch.setattr(kaggle_jobs, "status", lambda ref: "error")
    with pytest.raises(ProviderError, match="error"):
        kaggle_jobs.wait("user/job", sleep=lambda _: None)
