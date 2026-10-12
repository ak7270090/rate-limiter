import aiohttp
import pytest

from rateharness.client_factory import create_api_key
from rateharness.config import HarnessSettings
from rateharness.limit_accuracy import LimitPolicy, summarize_admissions
from rateharness.report_writer import HarnessReport, SuiteResult
from rateharness.traffic_patterns import RequestTarget, send_steady, wait_for_room_in_window

pytestmark = [pytest.mark.anyio, pytest.mark.accuracy]


async def test_steady_traffic_on_one_key_stays_within_limit(
    http_session: aiohttp.ClientSession,
    harness_settings: HarnessSettings,
    harness_report: HarnessReport,
    request: pytest.FixtureRequest,
) -> None:
    target = RequestTarget(harness_settings.per_key_method, harness_settings.per_key_route)
    policy = LimitPolicy(harness_settings.per_key_limit, harness_settings.per_key_window_seconds)
    sending_seconds = (
        harness_settings.accuracy_request_count / harness_settings.accuracy_rate_per_second
    )
    await wait_for_room_in_window(policy.window_seconds, sending_seconds + 1.0)

    responses = await send_steady(
        http_session,
        target,
        create_api_key("accuracy"),
        harness_settings.accuracy_request_count,
        harness_settings.accuracy_rate_per_second,
    )
    summary = summarize_admissions(responses, policy, harness_settings.tolerance_percent)

    harness_report.record(
        request.node.nodeid,
        SuiteResult(
            suite="accuracy",
            route=f"{target.method} {target.path}",
            limit=f"{policy.limit} / {policy.window_seconds:g} s",
            admitted=str(summary.admitted),
            detail=f"{len(responses)} sent at {harness_settings.accuracy_rate_per_second:g}/s; "
            f"over-admission {summary.over_admission_percent:.0f}%",
        ),
    )
    assert summary.is_within_limit, summary.describe()
