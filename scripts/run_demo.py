from __future__ import annotations

import asyncio
from datetime import datetime

from app.core.config import get_settings
from app.providers.football.factory import build_football_provider
from app.providers.llm.factory import build_llm_router
from app.repositories.database import Database
from app.services.arabic import telegram_prediction_text
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    await database.create_all()
    provider = build_football_provider(settings)
    service = PredictionService(
        settings=settings,
        provider=provider,
        database=database,
        explanations=ExplanationService(build_llm_router(settings)),
        broker=PredictionEventBroker(),
    )
    pre = await service.pre_match("demo-match-001")
    print("=== PRE-MATCH ===")
    print(telegram_prediction_text(pre, arabic_digits=settings.arabic_digits_enabled))
    live = await service.live(
        "demo-match-001",
        generated_at=datetime.fromisoformat("2026-07-06T19:44:00+00:00"),
        event_limit=7,
    )
    print("\n=== LIVE REPLAY AFTER EVENT 7 ===")
    print(telegram_prediction_text(live, arabic_digits=settings.arabic_digits_enabled))
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
