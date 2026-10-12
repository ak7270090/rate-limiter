"""Parse and check the IETF ``RateLimit`` / ``RateLimit-Policy`` headers and ``Retry-After``."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rateharness.constants import (
    QUOTA_PARAMETER,
    RATE_LIMIT_HEADER,
    RATE_LIMIT_POLICY_HEADER,
    REMAINING_PARAMETER,
    RESET_PARAMETER,
    RETRY_AFTER_HEADER,
    STATUS_OK,
    STATUS_TOO_MANY_REQUESTS,
    WINDOW_PARAMETER,
)
from rateharness.traffic_patterns import ObservedResponse


@dataclass(frozen=True)
class RateLimitHeaders:
    """The first policy in ``RateLimit-Policy`` and the matching ``RateLimit`` item."""

    policy_name: str
    quota: int
    window_seconds: int
    remaining: int
    reset_seconds: int


@dataclass(frozen=True)
class ExpectedHeaderPolicy:
    """The policy the headers should announce."""

    policy_name: str
    quota: int
    window_seconds: int


def parse_structured_item(header_value: str) -> tuple[str, dict[str, str]]:
    """Parse the first item of a structured-field list: ``"name";a=1;b=2``."""
    first_item = header_value.split(",")[0].strip()
    name, *parameters = first_item.split(";")
    parsed_parameters = {}
    for parameter in parameters:
        key, _, value = parameter.strip().partition("=")
        parsed_parameters[key] = value
    return name.strip().strip('"'), parsed_parameters


def parse_rate_limit_headers(headers: Mapping[str, str]) -> RateLimitHeaders | None:
    """Read both headers, or ``None`` if either is missing or malformed."""
    policy_value = headers.get(RATE_LIMIT_POLICY_HEADER)
    limit_value = headers.get(RATE_LIMIT_HEADER)
    if policy_value is None or limit_value is None:
        return None
    policy_name, policy_parameters = parse_structured_item(policy_value)
    _, limit_parameters = parse_structured_item(limit_value)
    try:
        return RateLimitHeaders(
            policy_name=policy_name,
            quota=int(policy_parameters[QUOTA_PARAMETER]),
            window_seconds=int(policy_parameters[WINDOW_PARAMETER]),
            remaining=int(limit_parameters[REMAINING_PARAMETER]),
            reset_seconds=int(limit_parameters[RESET_PARAMETER]),
        )
    except (KeyError, ValueError):
        return None


def find_header_problems(
    responses: Sequence[ObservedResponse], expected: ExpectedHeaderPolicy
) -> list[str]:
    """Problems in a sequence of responses sent one after another for one key."""
    problems: list[str] = []
    previous_remaining: int | None = None
    for index, response in enumerate(responses):
        if response.status_code not in (STATUS_OK, STATUS_TOO_MANY_REQUESTS):
            problems.append(f"#{index}: unexpected status {response.status_code}")
            continue
        parsed = parse_rate_limit_headers(response.headers)
        if parsed is None:
            problems.append(f"#{index}: missing or malformed RateLimit headers")
            continue
        if (parsed.policy_name, parsed.quota, parsed.window_seconds) != (
            expected.policy_name,
            expected.quota,
            expected.window_seconds,
        ):
            problems.append(f"#{index}: policy {parsed} does not match {expected}")
        if previous_remaining is not None and parsed.remaining > previous_remaining + 1:
            problems.append(f"#{index}: remaining rose from {previous_remaining}")
        previous_remaining = parsed.remaining
        if response.status_code == STATUS_TOO_MANY_REQUESTS:
            problems.extend(_find_rejection_problems(index, response, parsed))
    return problems


def _find_rejection_problems(
    index: int, response: ObservedResponse, parsed: RateLimitHeaders
) -> list[str]:
    problems = []
    retry_after = response.headers.get(RETRY_AFTER_HEADER, "")
    if not retry_after.isdigit() or int(retry_after) < 1:
        problems.append(
            f"#{index}: 429 needs Retry-After as whole seconds >= 1, got {retry_after!r}"
        )
    if parsed.remaining != 0:
        problems.append(f"#{index}: 429 with remaining {parsed.remaining}")
    return problems
