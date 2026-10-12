import httpx
import pytest

from rateharness.limit_accuracy import LimitPolicy, max_admitted_in_window, summarize_admissions
from rateharness.traffic_patterns import ObservedResponse


def make_response(sent_at: float, status_code: int, replica: str = "r1") -> ObservedResponse:
    return ObservedResponse(
        sent_at=sent_at,
        elapsed_seconds=0.001,
        status_code=status_code,
        headers=httpx.Headers({"X-Replica-Id": replica}),
    )


def test_summary_accepts_exact_limit() -> None:
    responses = [make_response(i * 0.01, 200) for i in range(100)] + [
        make_response(1.0 + i * 0.01, 429) for i in range(50)
    ]

    summary = summarize_admissions(responses, LimitPolicy(100, 10.0), tolerance_percent=5)

    assert summary.admitted == 100
    assert summary.rejected == 50
    assert summary.is_within_limit
    assert summary.over_admission_percent == 0


def test_summary_flags_three_replicas_each_admitting_everything() -> None:
    responses = [make_response(i * 0.02, 200, replica=f"r{i % 3}") for i in range(150)]

    summary = summarize_admissions(responses, LimitPolicy(100, 10.0), tolerance_percent=5)

    assert not summary.is_within_limit
    assert summary.replicas_seen == {"r0", "r1", "r2"}
    assert summary.over_admission_percent == pytest.approx((150 - 129.8) / 129.8 * 100)
    assert "admitted 150" in summary.describe()


def test_summary_allows_refill_during_a_slow_batch() -> None:
    responses = [make_response(i * 0.1, 200) for i in range(110)]

    summary = summarize_admissions(responses, LimitPolicy(100, 10.0), tolerance_percent=0)

    assert summary.upper_bound == pytest.approx(100 + 100 * 10.9 / 10)
    assert summary.is_within_upper_bound


def test_summary_flags_unexpected_statuses() -> None:
    responses = [make_response(0.0, 200), make_response(0.1, 500)]

    summary = summarize_admissions(responses, LimitPolicy(100, 10.0), tolerance_percent=5)

    assert summary.other_statuses == 1
    assert not summary.is_within_upper_bound


def test_max_admitted_in_window_finds_straddle() -> None:
    before = [make_response(9.5 + i * 0.001, 200) for i in range(100)]
    after = [make_response(10.2 + i * 0.001, 200) for i in range(100)]
    later = [make_response(25.0, 200)]

    assert max_admitted_in_window(before + after + later, 10.0) == 200
    assert max_admitted_in_window(before + after + later, 0.5) == 100
    assert max_admitted_in_window([], 10.0) == 0
