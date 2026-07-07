from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.providers.football.factory import build_football_provider
from app.providers.llm.factory import build_llm_router
from app.repositories.database import Database
from app.scheduling.live_coordinator import LiveMatchCoordinator
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    database = Database(settings)
    await database.create_all()
    football_provider = build_football_provider(settings)
    llm_router = build_llm_router(settings)
    broker = PredictionEventBroker()
    explanations = ExplanationService(llm_router)
    prediction_service = PredictionService(
        settings=settings,
        provider=football_provider,
        database=database,
        explanations=explanations,
        broker=broker,
    )
    coordinator = LiveMatchCoordinator(
        settings=settings, provider=football_provider, predictions=prediction_service
    )

    app.state.settings = settings
    app.state.database = database
    app.state.football_provider = football_provider
    app.state.llm_router = llm_router
    app.state.prediction_service = prediction_service
    app.state.live_coordinator = coordinator
    app.state.telegram_application = None

    if settings.live_polling_enabled:
        await coordinator.start()
    yield
    await coordinator.stop()
    for provider in football_provider.providers:
        close = getattr(provider, "close", None)
        if close:
            await close()
    await database.dispose()
