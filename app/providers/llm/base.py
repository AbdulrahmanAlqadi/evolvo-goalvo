from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMTransientError(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMPermanentError(LLMError):
    pass


class LLMValidationError(LLMError):
    pass


class LLMProvider(Protocol):
    name: str

    async def generate_structured(self, prompt: str, schema: type[T]) -> T: ...
    async def generate_text(self, prompt: str) -> str: ...
    async def healthcheck(self) -> bool: ...
