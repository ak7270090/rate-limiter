"""Sliding window counter: the current window's count plus a weighted share of the previous one."""

import math
from dataclasses import dataclass

from ratelab.algorithms.in_memory import InMemoryLimiter
from ratelab.constants import FLOAT_TOLERANCE
from ratelab.limiter import RateLimitDecision, build_decision


@dataclass(frozen=True, slots=True)
class SlidingWindowCounterState:
    window_start: float
    current_count: int
    previous_count: int


class SlidingWindowCounterLimiter(InMemoryLimiter[SlidingWindowCounterState]):
    """Estimates the rolling count as ``previous x (1 - elapsed fraction) + current``."""

    def decide(
        self, state: SlidingWindowCounterState | None, now: float, cost: int
    ) -> tuple[RateLimitDecision, SlidingWindowCounterState]:
        window_seconds = self.rule.window_seconds
        limit = self.rule.limit
        window_start = math.floor(now / window_seconds) * window_seconds
        current_count, previous_count = self._counts_for_window(state, window_start)
        previous_weight = 1 - (now - window_start) / window_seconds
        estimate = previous_count * previous_weight + current_count
        is_allowed = estimate + cost <= limit + FLOAT_TOLERANCE
        retry_after_seconds = 0.0
        if is_allowed:
            current_count += cost
            estimate += cost
        else:
            retry_after_seconds = (
                self._retry_time(window_start, current_count, previous_count, cost) - now
            )
        decision = build_decision(
            is_allowed=is_allowed,
            limit=limit,
            remaining=limit - estimate,
            reset_after_seconds=self._reset_time(window_start, current_count, previous_count) - now,
            retry_after_seconds=retry_after_seconds,
        )
        return decision, SlidingWindowCounterState(window_start, current_count, previous_count)

    def _counts_for_window(
        self, state: SlidingWindowCounterState | None, window_start: float
    ) -> tuple[int, int]:
        if state is None:
            return 0, 0
        if state.window_start == window_start:
            return state.current_count, state.previous_count
        if state.window_start == window_start - self.rule.window_seconds:
            return 0, state.current_count
        return 0, 0

    def _retry_time(
        self, window_start: float, current_count: int, previous_count: int, cost: int
    ) -> float:
        """Earliest time the estimate leaves room for ``cost``, if nothing else is admitted."""
        window_seconds = self.rule.window_seconds
        room_without_previous = self.rule.limit - current_count - cost
        if room_without_previous >= 0:
            elapsed_fraction = 1 - room_without_previous / previous_count
            return window_start + elapsed_fraction * window_seconds
        next_window_fraction = 1 - (self.rule.limit - cost) / current_count
        return window_start + window_seconds + next_window_fraction * window_seconds

    def _reset_time(self, window_start: float, current_count: int, previous_count: int) -> float:
        if current_count:
            return window_start + 2 * self.rule.window_seconds
        if previous_count:
            return window_start + self.rule.window_seconds
        return window_start
