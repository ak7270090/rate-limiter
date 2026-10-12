"""Per-key limiter state that disappears once the key's limit has fully reset."""

from typing import Generic, TypeVar

from ratelab.constants import DEFAULT_SWEEP_INTERVAL_OPERATIONS

StateT = TypeVar("StateT")


class KeyStateStore(Generic[StateT]):
    """A dict of key -> (state, expires_at), with lazy and periodic eviction of idle keys."""

    def __init__(self, sweep_interval_operations: int = DEFAULT_SWEEP_INTERVAL_OPERATIONS) -> None:
        self._entries: dict[str, tuple[StateT, float]] = {}
        self._sweep_interval_operations = sweep_interval_operations
        self._operations_since_sweep = 0

    def get(self, key: str, now: float) -> StateT | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        state, expires_at = entry
        if expires_at <= now:
            del self._entries[key]
            return None
        return state

    def put(self, key: str, state: StateT, expires_at: float, now: float) -> None:
        if expires_at <= now:
            self._entries.pop(key, None)
        else:
            self._entries[key] = (state, expires_at)
        self._operations_since_sweep += 1
        if self._operations_since_sweep >= self._sweep_interval_operations:
            self.evict_expired(now)

    def evict_expired(self, now: float) -> int:
        expired_keys = [key for key, (_, expires_at) in self._entries.items() if expires_at <= now]
        for key in expired_keys:
            del self._entries[key]
        self._operations_since_sweep = 0
        return len(expired_keys)

    def __len__(self) -> int:
        return len(self._entries)
