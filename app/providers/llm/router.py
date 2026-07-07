from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.providers.llm.base import LLMProvider

T = TypeVar("T", bound=BaseModel)


class LLMRouter:
    def __init__(self, providers: list[LLMProvider]) -> None:
        self.providers = providers

    async def generate_structured(self, prompt: str, schema: type[T]) -> tuple[T, str]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.generate_structured(prompt, schema), provider.name
            except Exception as exc:
                errors.append(f"{provider.name}:{type(exc).__name__}")
        raise RuntimeError("all LLM providers failed: " + ", ".join(errors))

    async def healthcheck(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for provider in self.providers:
            try:
                result[provider.name] = await provider.healthcheck()
            except Exception:
                result[provider.name] = False
        return result
