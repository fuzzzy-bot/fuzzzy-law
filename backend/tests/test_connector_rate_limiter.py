"""Tests for the in-memory sliding-window limiter the public connector runs with."""

from __future__ import annotations

from app.services.connector_rate_limiter import SlidingWindowLimiter, check_memory_rate_limit


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestSlidingWindow:
    def test_allows_up_to_the_limit_then_says_when_to_retry(self):
        clock = Clock()
        limiter = SlidingWindowLimiter(clock=clock)
        assert [limiter.check("a", 2, 60)[0] for _ in range(2)] == [True, True]
        clock.now += 20
        assert limiter.check("a", 2, 60) == (False, 41)

    def test_window_slides(self):
        clock = Clock()
        limiter = SlidingWindowLimiter(clock=clock)
        limiter.check("a", 2, 60)
        clock.now += 30
        limiter.check("a", 2, 60)
        clock.now += 31                       # the first request is now over a minute old
        assert limiter.check("a", 2, 60) == (True, 0)
        assert limiter.check("a", 2, 60)[0] is False

    def test_refused_requests_do_not_extend_the_block(self):
        clock = Clock()
        limiter = SlidingWindowLimiter(clock=clock)
        limiter.check("a", 1, 60)
        for _ in range(50):
            clock.now += 1
            assert limiter.check("a", 1, 60)[0] is False
        clock.now += 11
        assert limiter.check("a", 1, 60)[0] is True

    def test_callers_are_counted_apart(self):
        limiter = SlidingWindowLimiter(clock=Clock())
        assert limiter.check("a", 1, 60)[0] and limiter.check("b", 1, 60)[0]
        assert not limiter.check("a", 1, 60)[0]

    def test_zero_limit_refuses(self):
        assert SlidingWindowLimiter(clock=Clock()).check("a", 0, 60) == (False, 60)


class TestMemoryBound:
    def test_finished_windows_are_forgotten_first(self):
        clock = Clock()
        limiter = SlidingWindowLimiter(max_keys=3, clock=clock)
        limiter.check("old-1", 5, 60)
        limiter.check("old-2", 5, 60)
        clock.now += 61
        limiter.check("fresh", 5, 60)
        limiter.check("new", 5, 60)
        assert len(limiter) == 2
        assert limiter.check("fresh", 1, 60)[0] is False     # still remembered

    def test_never_holds_more_than_the_cap(self):
        limiter = SlidingWindowLimiter(max_keys=100, clock=Clock())
        for n in range(1000):
            limiter.check(f"caller-{n}", 5, 60)
        assert len(limiter) == 100


async def test_module_limiter_has_the_redis_call_shape():
    assert await check_memory_rate_limit("shape-test", 1, 60.0) == (True, 0)
    allowed, retry_after = await check_memory_rate_limit("shape-test", 1, 60.0)
    assert allowed is False and retry_after >= 1
