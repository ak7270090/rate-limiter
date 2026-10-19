"""Sliding window log: one timestamp per admitted request, exact over any rolling window."""

from collections import deque

from ratelab.rate_limiter import InMemoryLimiter, RateLimitDecision, build_decision


class SlidingWindowLogLimiter(InMemoryLimiter[deque[float]]):
    """Never admits more than ``limit`` in any ``window_seconds``; memory grows with the limit."""

    def decide(
        self, state: deque[float] | None, now: float, cost: int
    ) -> tuple[RateLimitDecision, deque[float]]:
        window_seconds = self.rule.window_seconds
        admitted_times = state if state is not None else deque()
        while admitted_times and admitted_times[0] <= now - window_seconds:
            admitted_times.popleft()
        is_allowed = len(admitted_times) + cost <= self.rule.limit
        retry_after_seconds = 0.0
        if is_allowed:
            admitted_times.extend([now] * cost)
        else:
            entries_to_expire = len(admitted_times) + cost - self.rule.limit
            retry_after_seconds = admitted_times[entries_to_expire - 1] + window_seconds - now
        decision = build_decision(
            is_allowed=is_allowed,
            limit=self.rule.limit,
            remaining=self.rule.limit - len(admitted_times),
            reset_after_seconds=admitted_times[-1] + window_seconds - now if admitted_times else 0,
            retry_after_seconds=retry_after_seconds,
        )
        return decision, admitted_times
