from __future__ import annotations

import asyncio
import json
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.observability.metrics import GEMINI_SLOT_HEALTH
from app.providers.llm.base import LLMPermanentError, LLMTransientError
from app.providers.llm.key_pool import GeminiKeyPool

T = TypeVar("T", bound=BaseModel)


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool = GeminiKeyPool(
            settings.gemini_keys,
            strategy=settings.gemini_key_selection_strategy,
            cooldown_seconds=settings.gemini_key_cooldown_seconds,
        )

    async def _call(self, prompt: str, response_schema: dict | None = None) -> str:
        if not self.pool.slots:
            raise LLMPermanentError("no Gemini keys configured")
        attempted: set[int] = set()
        max_attempts = min(self.settings.gemini_max_attempts_per_request, len(self.pool.slots))
        for _ in range(max_attempts):
            slot = await self.pool.acquire(attempted)
            if slot is None:
                break
            attempted.add(slot.slot)
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=slot.key)
                config = types.GenerateContentConfig(
                    temperature=self.settings.llm_temperature,
                    max_output_tokens=self.settings.llm_max_output_tokens,
                    response_mime_type="application/json" if response_schema else "text/plain",
                    response_json_schema=response_schema,
                )
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=self.settings.llm_model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self.settings.llm_timeout_seconds,
                )
                await self.pool.mark_success(slot.slot)
                GEMINI_SLOT_HEALTH.labels(str(slot.slot)).set(1)
                return response.text or ""
            except Exception as exc:
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                text = str(exc).lower()
                if (
                    status in {401, 403}
                    or "api key not valid" in text
                    or "permission denied" in text
                ):
                    await self.pool.mark_permanent_failure(slot.slot)
                    GEMINI_SLOT_HEALTH.labels(str(slot.slot)).set(0)
                    continue
                if (
                    status == 429
                    or status in {500, 502, 503, 504}
                    or isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                ):
                    retry_after = getattr(exc, "retry_after", None)
                    await self.pool.mark_transient_failure(slot.slot, retry_after)
                    GEMINI_SLOT_HEALTH.labels(str(slot.slot)).set(0)
                    continue
                raise LLMPermanentError(f"Gemini request failed: {type(exc).__name__}") from exc
        raise LLMTransientError("all eligible Gemini key slots failed or are cooling down")

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        text = await self._call(prompt, schema.model_json_schema())
        return schema.model_validate(json.loads(text))

    async def generate_text(self, prompt: str) -> str:
        return await self._call(prompt)

    async def healthcheck(self) -> bool:
        return bool(self.pool.slots)
