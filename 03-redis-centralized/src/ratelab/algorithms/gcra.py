"""GCRA (generic cell rate algorithm): token bucket behaviour from one stored timestamp."""

from ratelab.algorithms.in_memory import InMemoryLimiter
from ratelab.constants import FLOAT_TOLERANCE
from ratelab.limiter import RateLimitDecision, build_decision


class GcraLimiter(InMemoryLimiter[float]):
    """Stores the theoretical arrival time (TAT) of the next request.

    Each request pushes TAT forward by one emission interval (``window / limit``). A request is
    allowed while TAT stays within ``capacity`` intervals of now.
    """

    def decide(self, state: float | None, now: float, cost: int) -> tuple[RateLimitDecision, float]:
        emission_interval = self.rule.window_seconds / self.rule.limit
        burst_tolerance = emission_interval * self.rule.capacity
        theoretical_arrival = max(state if state is not None else now, now)
        new_theoretical_arrival = theoretical_arrival + emission_interval * cost
        allow_at = new_theoretical_arrival - burst_tolerance
        is_allowed = allow_at <= now + FLOAT_TOLERANCE
        stored_arrival = new_theoretical_arrival if is_allowed else theoretical_arrival
        decision = build_decision(
            is_allowed=is_allowed,
            limit=self.rule.capacity,
            remaining=(burst_tolerance - (stored_arrival - now)) / emission_interval
            + FLOAT_TOLERANCE,
            reset_after_seconds=stored_arrival - now,
            retry_after_seconds=allow_at - now,
        )
        return decision, stored_arrival
