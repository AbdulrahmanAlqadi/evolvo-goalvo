from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.providers.football.factory import build_football_provider
from app.providers.llm.factory import build_llm_router
from app.repositories.database import Database
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService
from app.telegram.app import build_telegram_application


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.telegram_enabled:
        raise SystemExit("Set TELEGRAM_ENABLED=true and TELEGRAM_BOT_TOKEN before starting the bot")
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
    application = build_telegram_application(settings, provider, service)
    if settings.telegram_mode == "webhook":
        raise SystemExit("Webhook mode is served by FastAPI; run uvicorn app.main:app")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
