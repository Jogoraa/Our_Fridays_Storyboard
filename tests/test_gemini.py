import pytest

from pipeline import gemini
from pipeline.common import ProviderError, QuotaError, RetryableError

PER_MINUTE = '{"error":{"message":"Rate limit exceeded for model gemini-3.8-flash (limit: 5 requests per minute on Free Tier). Please retry in 12s or upgrade","code":"rate_limited"}}'
PER_DAY = '{"error":{"message":"Rate limit exceeded for model gemini-3.8-flash (limit: 20 requests per day on Free Tier). Please retry in 56m50s or upgrade","code":"rate_limited"}}'


def test_retry_delay_is_parsed_from_the_message():
    assert gemini.retry_delay("Please retry in 12s or") == 12.0
    assert gemini.retry_delay("Please retry in 56m50s or") == 56 * 60 + 50
    assert gemini.retry_delay("Please retry in 1h2m3s.") == 3723.0
    assert gemini.retry_delay("no hint here") is None


def test_per_minute_limit_is_retryable_with_the_delay():
    with pytest.raises(RetryableError) as info:
        gemini.raise_for_status(429, PER_MINUTE)
    assert info.value.retry_after == 12.0


def test_per_day_limit_is_a_quota_error_not_a_retry():
    with pytest.raises(QuotaError, match="per day"):
        gemini.raise_for_status(429, PER_DAY)


def test_server_error_is_retryable_and_bad_request_is_not():
    with pytest.raises(RetryableError):
        gemini.raise_for_status(503, "high demand")
    with pytest.raises(ProviderError) as info:
        gemini.raise_for_status(404, "Model not found")
    assert not isinstance(info.value, (QuotaError,))
    gemini.raise_for_status(200, "{}")
