"""Compare how many requests got through with what the configured limit allows."""

from collections.abc import Sequence
from dataclasses import dataclass

from rateharness.constants import STATUS_OK, STATUS_TOO_MANY_REQUESTS
from rateharness.traffic_patterns import ObservedResponse


@dataclass(frozen=True)
class LimitPolicy:
    """A limit of ``limit`` requests per ``window_seconds``."""

    limit: int
    window_seconds: float


@dataclass(frozen=True)
class AdmissionSummary:
    """Admitted vs allowed for one batch of responses.

    Any correct algorithm starting from an empty limit admits at most ``limit`` at once plus
    what refills while the batch is being sent (``limit * elapsed / window``).
    """

    admitted: int
    rejected: int
    other_statuses: int
    elapsed_seconds: float
    allowed_maximum: float
    upper_bound: float
    lower_bound: float
    replicas_seen: frozenset[str]

    @property
    def over_admission_percent(self) -> float:
        """How much more got through than any correct limiter allows, in percent of that."""
        return max(self.admitted - self.allowed_maximum, 0.0) / self.allowed_maximum * 100

    @property
    def is_within_upper_bound(self) -> bool:
        return self.admitted <= self.upper_bound and self.other_statuses == 0

    @property
    def is_within_limit(self) -> bool:
        return self.is_within_upper_bound and self.admitted >= self.lower_bound

    def describe(self) -> str:
        return (
            f"admitted {self.admitted}, rejected {self.rejected}, other {self.other_statuses}, "
            f"allowed up to {self.upper_bound:.0f} over {self.elapsed_seconds:.2f} s, "
            f"replicas {sorted(self.replicas_seen)}"
        )


def summarize_admissions(
    responses: Sequence[ObservedResponse], policy: LimitPolicy, tolerance_percent: float
) -> AdmissionSummary:
    """Count admitted and rejected responses and the bounds a correct limiter must respect."""
    admitted = sum(1 for response in responses if response.status_code == STATUS_OK)
    rejected = sum(1 for response in responses if response.status_code == STATUS_TOO_MANY_REQUESTS)
    elapsed_seconds = (responses[-1].sent_at - responses[0].sent_at) if responses else 0.0
    tolerance = tolerance_percent / 100
    refill_during_batch = policy.limit * elapsed_seconds / policy.window_seconds
    allowed_maximum = policy.limit + refill_during_batch
    expected_minimum = min(len(responses), policy.limit)
    return AdmissionSummary(
        admitted=admitted,
        rejected=rejected,
        other_statuses=len(responses) - admitted - rejected,
        elapsed_seconds=elapsed_seconds,
        allowed_maximum=allowed_maximum,
        upper_bound=policy.limit * (1 + tolerance) + refill_during_batch,
        lower_bound=expected_minimum * (1 - tolerance),
        replicas_seen=frozenset(
            response.replica_id for response in responses if response.replica_id
        ),
    )


def max_admitted_in_window(responses: Sequence[ObservedResponse], window_seconds: float) -> int:
    """Largest number of admitted requests sent within any ``window_seconds`` span."""
    admitted_times = sorted(
        response.sent_at for response in responses if response.status_code == STATUS_OK
    )
    largest = 0
    window_start_index = 0
    for window_end_index, sent_at in enumerate(admitted_times):
        while sent_at - admitted_times[window_start_index] >= window_seconds:
            window_start_index += 1
        largest = max(largest, window_end_index - window_start_index + 1)
    return largest
