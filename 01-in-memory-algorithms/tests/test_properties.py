"""Invariants every algorithm must keep, checked on random arrival patterns with a fake clock."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ratelab.algorithm_registry import IN_MEMORY_LIMITERS, create_in_memory_limiter
from ratelab.clock import FakeClock
from ratelab.constants import (
    ALGORITHM_FIXED_WINDOW,
    ALGORITHM_GCRA,
    ALGORITHM_LEAKY_BUCKET,
    ALGORITHM_LEAKY_BUCKET_QUEUE,
    ALGORITHM_SLIDING_WINDOW_COUNTER,
    ALGORITHM_SLIDING_WINDOW_LOG,
    ALGORITHM_TOKEN_BUCKET,
)
from ratelab.rate_limiter import RateLimitRule

RULE = RateLimitRule(limit=5, window_seconds=1.0, burst=8)
START_SECONDS = 1_000.0
EPSILON = 1e-6

arrival_gaps = st.lists(st.one_of(st.just(0.0), st.floats(0.0, 0.6)), min_size=1, max_size=80)
costs = st.lists(st.integers(1, 3), min_size=80, max_size=80)


def admitted_times(algorithm: str, gaps: list[float]) -> list[float]:
    clock = FakeClock(START_SECONDS)
    limiter = create_in_memory_limiter(algorithm, RULE, clock)
    times = []
    for gap in gaps:
        clock.advance(gap)
        if limiter.try_acquire("k").is_allowed:
            times.append(clock.now())
    return times


@pytest.mark.parametrize("algorithm", IN_MEMORY_LIMITERS)
@settings(max_examples=150, deadline=None)
@given(gaps=arrival_gaps, request_costs=costs)
def test_remaining_stays_valid_and_retry_after_is_enough(
    algorithm: str, gaps: list[float], request_costs: list[int]
) -> None:
    clock = FakeClock(START_SECONDS)
    limiter = create_in_memory_limiter(algorithm, RULE, clock)
    for gap, cost in zip(gaps, request_costs, strict=False):
        clock.advance(gap)
        decision = limiter.try_acquire("k", cost)
        assert 0 <= decision.remaining <= decision.limit
        if not decision.is_allowed:
            clock.advance(decision.retry_after_seconds)
            assert limiter.try_acquire("k", cost).is_allowed


@pytest.mark.parametrize("algorithm", [ALGORITHM_FIXED_WINDOW, ALGORITHM_SLIDING_WINDOW_COUNTER])
@settings(max_examples=150, deadline=None)
@given(gaps=arrival_gaps)
def test_window_algorithms_never_exceed_limit_in_an_aligned_window(
    algorithm: str, gaps: list[float]
) -> None:
    times = admitted_times(algorithm, gaps)
    per_window: dict[int, int] = {}
    for admitted_at in times:
        window_index = math.floor(admitted_at / RULE.window_seconds)
        per_window[window_index] = per_window.get(window_index, 0) + 1
    assert all(count <= RULE.limit for count in per_window.values())


@settings(max_examples=150, deadline=None)
@given(gaps=arrival_gaps)
def test_sliding_log_never_exceeds_limit_in_any_rolling_window(gaps: list[float]) -> None:
    times = admitted_times(ALGORITHM_SLIDING_WINDOW_LOG, gaps)
    for start in times:
        in_window = [t for t in times if start <= t < start + RULE.window_seconds - EPSILON]
        assert len(in_window) <= RULE.limit


@pytest.mark.parametrize(
    "algorithm", [ALGORITHM_TOKEN_BUCKET, ALGORITHM_LEAKY_BUCKET, ALGORITHM_GCRA]
)
@settings(max_examples=150, deadline=None)
@given(gaps=arrival_gaps)
def test_bucket_algorithms_never_exceed_capacity_plus_refill(
    algorithm: str, gaps: list[float]
) -> None:
    times = admitted_times(algorithm, gaps)
    for first_index, first_time in enumerate(times):
        for last_index in range(first_index, len(times)):
            admitted = last_index - first_index + 1
            refill = RULE.rate_per_second * (times[last_index] - first_time)
            assert admitted <= RULE.capacity + refill + EPSILON


@settings(max_examples=150, deadline=None)
@given(gaps=arrival_gaps)
def test_leaky_queue_releases_requests_at_the_leak_rate(gaps: list[float]) -> None:
    clock = FakeClock(START_SECONDS)
    limiter = create_in_memory_limiter(ALGORITHM_LEAKY_BUCKET_QUEUE, RULE, clock)
    seconds_per_request = 1 / RULE.rate_per_second
    release_times = []
    for gap in gaps:
        clock.advance(gap)
        decision = limiter.try_acquire("k")
        if decision.is_allowed:
            assert decision.delay_seconds <= RULE.capacity * seconds_per_request + EPSILON
            release_times.append(clock.now() + decision.delay_seconds)
    for earlier, later in zip(release_times, release_times[1:], strict=False):
        assert later - earlier >= seconds_per_request - EPSILON
