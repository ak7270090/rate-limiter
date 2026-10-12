import httpx
import pytest

from rateharness.client_factory import create_api_key
from rateharness.config import HarnessSettings
from rateharness.limit_accuracy import LimitPolicy, max_admitted_in_window, summarize_admissions
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import RequestTarget, send_boundary_straddle

pytestmark = [pytest.mark.anyio, pytest.mark.boundary_burst]


async def test_bursts_around_window_reset_stay_within_limit(
    http_client: httpx.AsyncClient,
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    target = RequestTarget(harness_settings.per_key_method, harness_settings.per_key_route)
    policy = LimitPolicy(harness_settings.per_key_limit, harness_settings.per_key_window_seconds)

    responses = await send_boundary_straddle(
        http_client,
        target,
        create_api_key("boundary"),
        burst_size=policy.limit,
        window_seconds=policy.window_seconds,
        lead_seconds=harness_settings.boundary_lead_seconds,
        after_seconds=harness_settings.boundary_after_seconds,
        max_parallel_requests=harness_settings.max_parallel_requests,
    )
    summary = summarize_admissions(responses, policy, harness_settings.tolerance_percent)
    largest_in_window = max_admitted_in_window(responses, policy.window_seconds)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="boundary_burst",
            route=f"{target.method} {target.path}",
            limit=f"{policy.limit} / {policy.window_seconds:g} s",
            admitted=str(largest_in_window),
            detail=f"2 bursts of {policy.limit} {summary.elapsed_seconds:.2f} s apart "
            f"around a window reset; allowed up to {summary.upper_bound:.0f}",
        ),
    )
    assert largest_in_window <= summary.upper_bound, summary.describe()
