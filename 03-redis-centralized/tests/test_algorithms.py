import pytest

from ratelab.algorithms.fixed_window import FixedWindowLimiter
from ratelab.algorithms.gcra import GcraLimiter
from ratelab.algorithms.leaky_bucket import LeakyBucketLimiter, LeakyBucketQueueLimiter
from ratelab.algorithms.sliding_window_counter import SlidingWindowCounterLimiter
from ratelab.algorithms.sliding_window_log import SlidingWindowLogLimiter
from ratelab.algorithms.token_bucket import TokenBucketLimiter
from ratelab.clock import FakeClock
from ratelab.limiter import RateLimitRule

RULE = RateLimitRule(limit=100, window_seconds=10.0)
WINDOW_START = 1_000.0


def admit_many(limiter, count: int, key: str = "k42") -> int:
    return sum(limiter.try_acquire(key).is_allowed for _ in range(count))


def test_fixed_window_resets_at_window_boundary_and_allows_double_around_it() -> None:
    clock = FakeClock(WINDOW_START + 9.5)
    limiter = FixedWindowLimiter(RULE, clock)

    assert admit_many(limiter, 101) == 100
    rejected = limiter.try_acquire("k42")
    assert rejected.retry_after_seconds == pytest.approx(0.5, abs=1e-5)
    assert rejected.remaining == 0

    clock.set(WINDOW_START + 10.2)
    assert admit_many(limiter, 100) == 100


def test_sliding_window_log_waits_for_the_oldest_entry_to_expire() -> None:
    clock = FakeClock(WINDOW_START)
    limiter = SlidingWindowLogLimiter(RULE, clock)
    admit_many(limiter, 60)
    clock.advance(4.0)
    admit_many(limiter, 40)

    rejected = limiter.try_acquire("k42")
    assert not rejected.is_allowed
    assert rejected.retry_after_seconds == pytest.approx(6.0, abs=1e-5)

    clock.advance(6.0)
    assert admit_many(limiter, 61) == 60


def test_sliding_window_counter_weights_previous_window() -> None:
    clock = FakeClock(WINDOW_START + 5.0)
    limiter = SlidingWindowCounterLimiter(RULE, clock)
    admit_many(limiter, 80)

    clock.set(WINDOW_START + 14.0)
    admit_many(limiter, 30)
    decision = limiter.try_acquire("k42")

    # 80 x 0.6 + 31 = 79 -> 21 left
    assert decision.is_allowed
    assert decision.remaining == 21


def test_sliding_window_counter_retry_time_in_current_and_next_window() -> None:
    clock = FakeClock(WINDOW_START + 5.0)
    limiter = SlidingWindowCounterLimiter(RULE, clock)
    admit_many(limiter, 100)
    clock.set(WINDOW_START + 10.0)

    rejected = limiter.try_acquire("k42")
    clock.advance(rejected.retry_after_seconds)
    assert limiter.try_acquire("k42").is_allowed

    clock.set(WINDOW_START + 30.0)
    admit_many(limiter, 100)
    rejected_full_window = limiter.try_acquire("k42")
    assert rejected_full_window.retry_after_seconds == pytest.approx(10.1, abs=1e-3)


def test_token_bucket_bursts_to_capacity_then_refills_at_rate() -> None:
    clock = FakeClock(WINDOW_START)
    limiter = TokenBucketLimiter(RateLimitRule(10, 1.0, burst=20), clock)

    assert admit_many(limiter, 25) == 20
    clock.advance(0.5)
    assert admit_many(limiter, 10) == 5
    assert limiter.try_acquire("k42").retry_after_seconds == pytest.approx(0.1, abs=1e-5)


def test_leaky_bucket_meter_drains_at_rate() -> None:
    clock = FakeClock(WINDOW_START)
    limiter = LeakyBucketLimiter(RateLimitRule(10, 1.0), clock)

    assert admit_many(limiter, 12) == 10
    clock.advance(0.3)
    assert admit_many(limiter, 5) == 3


def test_leaky_bucket_queue_delays_instead_of_rejecting() -> None:
    clock = FakeClock(WINDOW_START)
    limiter = LeakyBucketQueueLimiter(RateLimitRule(10, 1.0, burst=3), clock)

    delays = [limiter.try_acquire("k42").delay_seconds for _ in range(3)]
    overflow = limiter.try_acquire("k42")

    assert delays == pytest.approx([0.0, 0.1, 0.2])
    assert not overflow.is_allowed
    assert overflow.retry_after_seconds == pytest.approx(0.1, abs=1e-5)


def test_gcra_admits_like_a_token_bucket() -> None:
    clock = FakeClock(WINDOW_START)
    gcra = GcraLimiter(RateLimitRule(10, 1.0, burst=20), clock)
    bucket = TokenBucketLimiter(RateLimitRule(10, 1.0, burst=20), clock)

    pattern = []
    for gap in [0, 0, 0.05, 0.3, 0, 0.01, 0.5, 0, 0, 0.2] * 6:
        clock.advance(gap)
        pattern.append((gcra.try_acquire("k").is_allowed, bucket.try_acquire("k").is_allowed))

    assert all(gcra_allowed == bucket_allowed for gcra_allowed, bucket_allowed in pattern)
