"""``RateLimit`` / ``RateLimit-Policy`` (IETF httpapi draft) and ``Retry-After`` headers."""

import math

from ratelab.constants import RATE_LIMIT_HEADER, RATE_LIMIT_POLICY_HEADER, RETRY_AFTER_HEADER
from ratelab.policy_registry import RoutePolicy
from ratelab.rate_limiter import RateLimitDecision


def build_rate_limit_headers(policy: RoutePolicy, decision: RateLimitDecision) -> dict[str, str]:
    """Headers for every limited response; a rejection also gets ``Retry-After``."""
    remaining = min(decision.remaining, policy.limit)
    headers = {
        RATE_LIMIT_POLICY_HEADER: f'"{policy.name}";q={policy.limit};w={policy.window_seconds:g}',
        RATE_LIMIT_HEADER: (
            f'"{policy.name}";r={remaining};t={math.ceil(decision.reset_after_seconds)}'
        ),
    }
    if not decision.is_allowed and decision.retry_after_seconds is not None:
        headers[RETRY_AFTER_HEADER] = str(max(math.ceil(decision.retry_after_seconds), 1))
    return headers
