from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.providers.football.composite import CompositeFootballProvider
from app.services.predictions import PredictionService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PollerState:
    running: bool = False
    iterations: int = 0
    live_matches: int = 0
    last_error: str | None = None


class LiveMatchCoordinator:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: CompositeFootballProvider,
        predictions: PredictionService,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.predictions = predictions
        self.state = PollerState()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

    async def start(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            self._stop.clear()
            self.state.running = True
            self._task = asyncio.create_task(self._run(), name="live-match-coordinator")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.state.running = False

    async def _run(self) -> None:
        interval = self.settings.live_poll_interval_seconds
        while not self._stop.is_set():
            try:
                matches = await self.provider.get_live_matches()
                self.state.live_matches = len(matches)
                for match in matches:
                    await self.predictions.live(match.id)
                self.state.iterations += 1
                self.state.last_error = None
                interval = max(
                    self.settings.live_poll_min_interval_seconds,
                    self.settings.live_poll_interval_seconds,
                )
            except Exception as exc:
                self.state.last_error = type(exc).__name__
                logger.warning("live polling iteration failed: %s", type(exc).__name__)
                interval = min(
                    self.settings.live_poll_max_interval_seconds,
                    max(interval * 2, self.settings.live_poll_interval_seconds),
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                continue
