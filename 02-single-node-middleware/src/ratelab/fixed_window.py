"""Fixed window counter: one count per key per epoch-aligned window."""

import math
from dataclasses import dataclass

from ratelab.rate_limiter import InMemoryLimiter, RateLimitDecision, build_decision


@dataclass(frozen=True, slots=True)
class FixedWindowState:
    window_start: float
    count: int


class FixedWindowLimiter(InMemoryLimiter[FixedWindowState]):
    """Allows ``limit`` per window; up to twice that can pass around a window reset."""

    def decide(
        self, state: FixedWindowState | None, now: float, cost: int
    ) -> tuple[RateLimitDecision, FixedWindowState]:
        window_seconds = self.rule.window_seconds
        window_start = math.floor(now / window_seconds) * window_seconds
        count = state.count if state and state.window_start == window_start else 0
        reset_after_seconds = window_start + window_seconds - now
        is_allowed = count + cost <= self.rule.limit
        if is_allowed:
            count += cost
        decision = build_decision(
            is_allowed=is_allowed,
            limit=self.rule.limit,
            remaining=self.rule.limit - count,
            reset_after_seconds=reset_after_seconds,
            retry_after_seconds=reset_after_seconds,
        )
        return decision, FixedWindowState(window_start, count)
