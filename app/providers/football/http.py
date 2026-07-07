from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.core.security import validate_outbound_url
from app.observability.metrics import PROVIDER_REQUESTS
from app.providers.football.base import (
    FootballProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
)


@dataclass(slots=True)
class CircuitState:
    failures: int = 0
    opened_until: float = 0.0


class SlidingBudget:
    def __init__(self, per_minute: int, per_day: int) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self.minute_calls: deque[float] = deque()
        self.day_calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self.minute_calls and now - self.minute_calls[0] >= 60:
                self.minute_calls.popleft()
            while self.day_calls and now - self.day_calls[0] >= 86400:
                self.day_calls.popleft()
            if self.per_minute and len(self.minute_calls) >= self.per_minute:
                raise ProviderRateLimited(60 - (now - self.minute_calls[0]))
            if self.per_day and len(self.day_calls) >= self.per_day:
                raise ProviderRateLimited(86400 - (now - self.day_calls[0]))
            self.minute_calls.append(now)
            self.day_calls.append(now)


class SafeHttpProvider:
    name = "http"

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str,
        headers: dict[str, str] | None = None,
        per_minute: int = 10,
        per_day: int = 100,
    ) -> None:
        validate_outbound_url(base_url, settings)
        self.settings = settings
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(settings.football_request_timeout_seconds),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self.budget = SlidingBudget(per_minute, per_day)
        self.circuit = CircuitState()

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
            except Exception:
                return None

    async def _request_json(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = time.monotonic()
        if self.circuit.opened_until > now:
            raise ProviderUnavailable("provider circuit is open")
        await self.budget.acquire()

        attempts = self.settings.football_max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await self.client.request(method, path, params=params)
                if response.status_code == 429:
                    retry_after = self._retry_after(response)
                    PROVIDER_REQUESTS.labels(self.name, operation, "rate_limited").inc()
                    raise ProviderRateLimited(retry_after)
                if 400 <= response.status_code < 500:
                    PROVIDER_REQUESTS.labels(self.name, operation, "invalid_request").inc()
                    raise FootballProviderError(
                        f"provider rejected request ({response.status_code})"
                    )
                response.raise_for_status()
                if len(response.content) > 10_000_000:
                    raise FootballProviderError("provider response exceeded safe size")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise FootballProviderError("provider returned non-object JSON")
                self.circuit.failures = 0
                PROVIDER_REQUESTS.labels(self.name, operation, "ok").inc()
                return payload
            except ProviderRateLimited as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(min(exc.retry_after or 1.0, 5.0))
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(min(0.25 * (2**attempt) + random.random() * 0.1, 2.0))
            except (ValueError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(min(0.25 * (2**attempt), 2.0))

        self.circuit.failures += 1
        if self.circuit.failures >= 3:
            self.circuit.opened_until = time.monotonic() + 60
        PROVIDER_REQUESTS.labels(self.name, operation, "error").inc()
        if isinstance(last_error, ProviderRateLimited):
            raise last_error
        raise ProviderUnavailable(f"provider request failed: {type(last_error).__name__}")
