"""``RateLimit`` / ``RateLimit-Policy`` (IETF httpapi draft) and ``Retry-After`` headers.

Every tier is listed, in policy order, e.g.
``RateLimit-Policy: "reports-day";q=50;w=86400, "user";q=200;w=10``.
"""

import math

from ratelab.constants import RATE_LIMIT_HEADER, RATE_LIMIT_POLICY_HEADER, RETRY_AFTER_HEADER
from ratelab.limiter import RateLimitDecision
from ratelab.policies.route_policies import RoutePolicy


def build_rate_limit_headers(policy: RoutePolicy, decision: RateLimitDecision) -> dict[str, str]:
    """Headers for every limited response; a rejection also gets ``Retry-After``."""
    headers = {
        RATE_LIMIT_POLICY_HEADER: ", ".join(
            f'"{tier.name}";q={tier.limit};w={tier.window_seconds:g}' for tier in policy.tiers
        )
    }
    if decision.tier_states:
        headers[RATE_LIMIT_HEADER] = ", ".join(
            f'"{state.name}";r={min(state.remaining, state.limit)};'
            f"t={math.ceil(state.reset_after_seconds)}"
            for state in decision.tier_states
        )
    if not decision.is_allowed and decision.retry_after_seconds is not None:
        headers[RETRY_AFTER_HEADER] = str(max(math.ceil(decision.retry_after_seconds), 1))
    return headers
