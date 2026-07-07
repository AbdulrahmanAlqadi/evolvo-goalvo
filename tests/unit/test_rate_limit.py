import pytest

from app.core.rate_limit import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_recovers_after_window():
    now = [100.0]
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])

    assert (await limiter.check("client")).allowed
    assert (await limiter.check("client")).allowed
    rejected = await limiter.check("client")
    assert not rejected.allowed
    assert rejected.retry_after_seconds == 10

    now[0] = 110.1
    recovered = await limiter.check("client")
    assert recovered.allowed
    assert recovered.remaining == 1
