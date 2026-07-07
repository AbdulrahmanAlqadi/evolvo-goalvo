from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.providers.llm.base import LLMPermanentError, LLMTransientError

T = TypeVar("T", bound=BaseModel)


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.settings = settings
        self.base_url = (base_url or settings.openai_compatible_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_compatible_api_key
        self.model = model or settings.llm_model

    async def _chat(self, prompt: str, json_schema: dict | None = None) -> str:
        if not self.base_url:
            raise LLMPermanentError("OpenAI-compatible base URL is not configured")
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_output_tokens,
        }
        if json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": json_schema, "strict": True},
            }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise LLMTransientError(f"provider transient status {response.status_code}")
            if response.status_code >= 400:
                raise LLMPermanentError(f"provider rejected request ({response.status_code})")
            return response.json()["choices"][0]["message"]["content"]
        except httpx.RequestError as exc:
            raise LLMTransientError(type(exc).__name__) from exc

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        return schema.model_validate(
            json.loads(await self._chat(prompt, schema.model_json_schema()))
        )

    async def generate_text(self, prompt: str) -> str:
        return await self._chat(prompt)

    async def healthcheck(self) -> bool:
        return bool(self.base_url)
