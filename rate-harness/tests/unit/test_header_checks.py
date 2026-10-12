import httpx

from rateharness.header_checks import (
    ExpectedHeaderPolicy,
    find_header_problems,
    parse_rate_limit_headers,
    parse_structured_item,
)
from rateharness.traffic_patterns import ObservedResponse

EXPECTED = ExpectedHeaderPolicy(policy_name="items", quota=100, window_seconds=10)


def make_response(status_code: int, remaining: int, retry_after: str | None = None):
    headers = {
        "RateLimit-Policy": '"items";q=100;w=10',
        "RateLimit": f'"items";r={remaining};t=4',
    }
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return ObservedResponse(0.0, 0.001, status_code, httpx.Headers(headers))


def test_parse_structured_item_reads_name_and_parameters() -> None:
    assert parse_structured_item('"items";q=100;w=10, "day";q=50;w=86400') == (
        "items",
        {"q": "100", "w": "10"},
    )


def test_parse_rate_limit_headers_handles_missing_and_malformed() -> None:
    assert parse_rate_limit_headers({}) is None
    malformed = {"RateLimit-Policy": '"items";q=abc', "RateLimit": '"items";r=1;t=1'}
    assert parse_rate_limit_headers(malformed) is None
    parsed = parse_rate_limit_headers(make_response(200, 7).headers)
    assert parsed is not None
    assert (parsed.quota, parsed.window_seconds, parsed.remaining) == (100, 10, 7)


def test_consistent_sequence_has_no_problems() -> None:
    responses = [make_response(200, 2), make_response(200, 1), make_response(200, 0)]
    responses.append(make_response(429, 0, retry_after="4"))

    assert find_header_problems(responses, EXPECTED) == []


def test_problems_are_reported() -> None:
    missing = ObservedResponse(0.0, 0.001, 200, httpx.Headers({}))
    responses = [
        make_response(200, 1),
        make_response(200, 50),
        make_response(429, 3, retry_after="0.5"),
        missing,
        ObservedResponse(0.0, 0.001, 500, httpx.Headers({})),
    ]

    problems = find_header_problems(responses, ExpectedHeaderPolicy("other", 100, 10))

    assert any("does not match" in problem for problem in problems)
    assert any("remaining rose" in problem for problem in problems)
    assert any("Retry-After" in problem for problem in problems)
    assert any("429 with remaining 3" in problem for problem in problems)
    assert any("missing" in problem for problem in problems)
    assert any("unexpected status 500" in problem for problem in problems)
