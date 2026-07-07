from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum


class KeyHealth(StrEnum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(slots=True)
class KeySlot:
    slot: int
    key: str
    health: KeyHealth = KeyHealth.HEALTHY
    cooldown_until: float = 0.0
    last_used: float = 0.0
    consecutive_failures: int = 0


class GeminiKeyPool:
    def __init__(
        self, keys: list[str], *, strategy: str = "least_recently_used", cooldown_seconds: int = 60
    ) -> None:
        self.slots = [KeySlot(index + 1, key) for index, key in enumerate(keys)]
        self.strategy = strategy
        self.cooldown_seconds = cooldown_seconds
        self._lock = asyncio.Lock()
        self._round_robin_index = 0

    async def acquire(self, excluded: set[int] | None = None) -> KeySlot | None:
        excluded = excluded or set()
        async with self._lock:
            now = time.monotonic()
            for slot in self.slots:
                if slot.health == KeyHealth.COOLDOWN and slot.cooldown_until <= now:
                    slot.health = KeyHealth.HEALTHY
                    slot.consecutive_failures = 0
            available = [
                slot
                for slot in self.slots
                if slot.slot not in excluded and slot.health == KeyHealth.HEALTHY
            ]
            if not available:
                return None
            if self.strategy == "round_robin":
                slot = available[self._round_robin_index % len(available)]
                self._round_robin_index += 1
            else:
                slot = min(available, key=lambda item: item.last_used)
            slot.last_used = now
            return slot

    async def mark_success(self, slot_number: int) -> None:
        async with self._lock:
            slot = self._slot(slot_number)
            slot.health = KeyHealth.HEALTHY
            slot.consecutive_failures = 0
            slot.cooldown_until = 0.0

    async def mark_transient_failure(
        self, slot_number: int, retry_after: float | None = None
    ) -> None:
        async with self._lock:
            slot = self._slot(slot_number)
            slot.consecutive_failures += 1
            slot.health = KeyHealth.COOLDOWN
            slot.cooldown_until = time.monotonic() + max(1.0, retry_after or self.cooldown_seconds)

    async def mark_permanent_failure(self, slot_number: int) -> None:
        async with self._lock:
            slot = self._slot(slot_number)
            slot.consecutive_failures += 1
            slot.health = KeyHealth.PERMANENT_FAILURE
            slot.cooldown_until = float("inf")

    async def recovery_probe_candidates(self) -> list[KeySlot]:
        async with self._lock:
            now = time.monotonic()
            return [
                slot
                for slot in self.slots
                if slot.health == KeyHealth.COOLDOWN and slot.cooldown_until <= now
            ]

    def _slot(self, number: int) -> KeySlot:
        for slot in self.slots:
            if slot.slot == number:
                return slot
        raise KeyError(number)
