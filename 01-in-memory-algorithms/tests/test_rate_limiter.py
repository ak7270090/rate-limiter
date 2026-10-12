from pathlib import Path

import pytest

from ratelab.algorithm_registry import create_in_memory_limiter
from ratelab.benchmark import main
from ratelab.clock import FakeClock, SystemClock
from ratelab.key_state_store import KeyStateStore
from ratelab.rate_limiter import RateLimitRule, build_decision
from ratelab.token_bucket import TokenBucketLimiter

RULE = RateLimitRule(limit=10, window_seconds=1.0)


@pytest.mark.anyio
async def test_acquire_is_the_async_face_of_try_acquire() -> None:
    limiter = TokenBucketLimiter(RULE, FakeClock(100.0))

    decision = await limiter.acquire("k")

    assert decision.is_allowed
    assert decision.remaining == 9


def test_cost_outside_capacity_is_rejected_up_front() -> None:
    limiter = TokenBucketLimiter(RULE)

    with pytest.raises(ValueError, match="cost 11"):
        limiter.try_acquire("k", 11)
    with pytest.raises(ValueError):
        limiter.try_acquire("k", 0)


def test_build_decision_clamps_and_adds_retry_margin() -> None:
    allowed = build_decision(is_allowed=True, limit=5, remaining=-0.5, reset_after_seconds=-1)
    rejected = build_decision(
        is_allowed=False, limit=5, remaining=0, reset_after_seconds=2, retry_after_seconds=0.5
    )

    assert (allowed.remaining, allowed.reset_after_seconds, allowed.retry_after_seconds) == (
        0,
        0.0,
        None,
    )
    assert rejected.retry_after_seconds == pytest.approx(0.5, abs=1e-5)
    assert rejected.retry_after_seconds > 0.5


def test_idle_keys_are_evicted_once_their_limit_resets() -> None:
    clock = FakeClock(100.0)
    limiter = TokenBucketLimiter(RULE, clock)
    limiter.try_acquire("a")
    limiter.try_acquire("b")
    assert limiter.tracked_key_count == 2

    clock.advance(5.0)
    limiter.try_acquire("a")

    assert limiter.tracked_key_count == 2
    assert limiter.try_acquire("b").remaining == 9


def test_store_sweeps_expired_entries_periodically() -> None:
    store: KeyStateStore[int] = KeyStateStore(sweep_interval_operations=3)
    store.put("a", 1, expires_at=10.0, now=0.0)
    store.put("b", 2, expires_at=20.0, now=0.0)
    store.put("c", 3, expires_at=0.0, now=0.0)
    assert len(store) == 2

    store.put("d", 4, expires_at=30.0, now=15.0)
    store.put("e", 5, expires_at=30.0, now=15.0)
    store.put("f", 6, expires_at=30.0, now=15.0)

    assert store.get("a", now=15.0) is None
    assert len(store) == 4
    assert store.get("b", now=25.0) is None


def test_registry_and_system_clock() -> None:
    limiter = create_in_memory_limiter("gcra", RULE)

    assert isinstance(limiter.clock, SystemClock)
    assert limiter.clock.now() > 1_700_000_000
    with pytest.raises(KeyError):
        create_in_memory_limiter("unknown", RULE)


def test_benchmark_writes_comparison_for_every_algorithm(tmp_path: Path) -> None:
    main(
        [
            "--key-counts",
            "1",
            "10",
            "--operations",
            "100",
            "--memory-keys",
            "5",
            "--results-dir",
            str(tmp_path),
        ]
    )

    table = (tmp_path / "algorithm-comparison.md").read_text(encoding="utf-8")
    assert "| fixed_window |" in table
    assert "| gcra |" in table
    fixed_row = next(line for line in table.splitlines() if line.startswith("| fixed_window"))
    assert "| 100 | 200 |" in fixed_row
