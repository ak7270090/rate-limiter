import httpx
import pytest

from rateharness.client_factory import create_api_key
from rateharness.config import HarnessSettings
from rateharness.limit_accuracy import LimitPolicy, summarize_admissions
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import RequestTarget, send_fan_out

pytestmark = [pytest.mark.anyio, pytest.mark.concurrency]


async def test_parallel_requests_on_one_key_stay_within_limit(
    http_client: httpx.AsyncClient,
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    target = RequestTarget(harness_settings.per_key_method, harness_settings.per_key_route)
    policy = LimitPolicy(harness_settings.per_key_limit, harness_settings.per_key_window_seconds)

    responses = await send_fan_out(
        http_client,
        target,
        create_api_key("concurrency"),
        harness_settings.concurrency_client_count,
    )
    summary = summarize_admissions(responses, policy, harness_settings.tolerance_percent)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="concurrency",
            route=f"{target.method} {target.path}",
            limit=f"{policy.limit} / {policy.window_seconds:g} s",
            admitted=str(summary.admitted),
            detail=f"{len(responses)} parallel requests in {summary.elapsed_seconds:.2f} s; "
            f"over-admission {summary.over_admission_percent:.0f}%",
        ),
    )
    assert summary.is_within_limit, summary.describe()
