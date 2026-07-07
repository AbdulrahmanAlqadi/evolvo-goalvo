import asyncio

import pytest

from app.providers.llm.key_pool import GeminiKeyPool, KeyHealth


@pytest.mark.asyncio
async def test_lru_selection_and_cooldown():
    pool = GeminiKeyPool(["a", "b"], strategy="least_recently_used", cooldown_seconds=60)
    first = await pool.acquire()
    second = await pool.acquire({first.slot})
    assert first.slot != second.slot
    await pool.mark_transient_failure(first.slot, retry_after=10)
    selected = await pool.acquire()
    assert selected.slot == second.slot
    assert pool.slots[first.slot - 1].health == KeyHealth.COOLDOWN


@pytest.mark.asyncio
async def test_concurrent_acquire_is_safe():
    pool = GeminiKeyPool(["a", "b", "c"])
    slots = await asyncio.gather(*(pool.acquire() for _ in range(20)))
    assert all(slot is not None for slot in slots)
    assert all(1 <= slot.slot <= 3 for slot in slots)
