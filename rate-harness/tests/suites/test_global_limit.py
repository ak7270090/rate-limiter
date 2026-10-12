import pytest

from rateharness.client_factory import create_api_key, create_http_client
from rateharness.config import HarnessSettings
from rateharness.limit_accuracy import LimitPolicy, summarize_admissions
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import RequestTarget, send_parallel

pytestmark = [pytest.mark.anyio, pytest.mark.global_limit]


async def test_global_limit_holds_across_keys_and_replicas(
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    target = RequestTarget(harness_settings.global_method, harness_settings.global_route)
    policy = LimitPolicy(harness_settings.global_limit, harness_settings.global_window_seconds)
    api_keys = [create_api_key("global") for _ in range(harness_settings.global_key_count)]
    request_keys = [
        api_keys[index % len(api_keys)] for index in range(harness_settings.global_request_count)
    ]

    async with create_http_client(harness_settings, should_reuse_connections=False) as client:
        responses = await send_parallel(
            client, target, request_keys, harness_settings.max_parallel_requests
        )
    summary = summarize_admissions(responses, policy, harness_settings.tolerance_percent)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="global_limit",
            route=f"{target.method} {target.path}",
            limit=f"{policy.limit} / {policy.window_seconds:g} s, all keys",
            admitted=str(summary.admitted),
            detail=f"{len(responses)} requests from {len(api_keys)} keys over "
            f"{len(summary.replicas_seen)} replica(s) in {summary.elapsed_seconds:.2f} s",
        ),
    )
    assert len(summary.replicas_seen) >= harness_settings.expected_replica_count
    assert summary.is_within_upper_bound, summary.describe()
