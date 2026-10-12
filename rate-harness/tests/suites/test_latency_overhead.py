import statistics

import aiohttp
import pytest

from rateharness.client_factory import create_api_key
from rateharness.config import HarnessSettings
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import ObservedResponse, RequestTarget, send_sequential

pytestmark = [pytest.mark.anyio, pytest.mark.latency_overhead]

REQUESTS_PER_KEY = 50


def p95_milliseconds(responses: list[ObservedResponse]) -> float:
    return statistics.quantiles([r.elapsed_seconds for r in responses], n=20)[-1] * 1000


async def test_limiting_adds_little_latency(
    http_session: aiohttp.ClientSession,
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    baseline_target = RequestTarget("GET", harness_settings.baseline_route)
    limited_target = RequestTarget(harness_settings.per_key_method, harness_settings.per_key_route)
    sample_count = harness_settings.latency_sample_count

    baseline = await send_sequential(
        http_session, baseline_target, create_api_key("latency"), sample_count
    )
    limited: list[ObservedResponse] = []
    while len(limited) < sample_count:
        limited += await send_sequential(
            http_session, limited_target, create_api_key("latency"), REQUESTS_PER_KEY
        )
    baseline_p95 = p95_milliseconds(baseline)
    limited_p95 = p95_milliseconds(limited)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="latency_overhead",
            route=f"{limited_target.method} {limited_target.path}",
            limit="-",
            admitted="-",
            detail=f"p95 {limited_p95:.1f} ms vs {baseline_p95:.1f} ms on "
            f"{baseline_target.path} ({sample_count} sequential requests each)",
        ),
    )
    assert limited_p95 - baseline_p95 <= harness_settings.max_overhead_ms
