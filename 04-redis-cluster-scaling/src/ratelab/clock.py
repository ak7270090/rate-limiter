"""Time sources: the real clock for running, a fake one for tests and simulations."""

import time
from typing import Protocol


class Clock(Protocol):
    """Seconds since the Unix epoch."""

    def now(self) -> float: ...


class SystemClock:
    """Wall-clock time, so fixed windows line up across processes."""

    def now(self) -> float:
        return time.time()


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, start_seconds: float = 0.0) -> None:
        self._now = start_seconds

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def set(self, seconds: float) -> None:
        self._now = seconds
