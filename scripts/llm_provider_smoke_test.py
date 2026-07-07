from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.core.config import get_settings
from app.providers.llm.factory import build_llm_router


class SmokeResponse(BaseModel):
    headline_ar: str


async def main() -> None:
    router = build_llm_router(get_settings())
    if router is None:
        raise SystemExit("LLM is disabled; set LLM_ENABLED=true and configure credentials")
    result, provider = await router.generate_structured(
        'أعد JSON فقط: {"headline_ar": "اختبار"}', SmokeResponse
    )
    print(provider, result.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
