from __future__ import annotations

import asyncio
from collections import defaultdict

from app.schemas.predictions import PredictionResponse


class PredictionEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[PredictionResponse]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, match_id: str) -> asyncio.Queue[PredictionResponse]:
        queue: asyncio.Queue[PredictionResponse] = asyncio.Queue(maxsize=10)
        async with self._lock:
            self._subscribers[match_id].add(queue)
        return queue

    async def unsubscribe(self, match_id: str, queue: asyncio.Queue[PredictionResponse]) -> None:
        async with self._lock:
            self._subscribers[match_id].discard(queue)

    async def publish(self, prediction: PredictionResponse) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(prediction.match_id, set()))
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(prediction)
