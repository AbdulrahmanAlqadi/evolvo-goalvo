from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.providers.football.composite import CompositeFootballProvider
from app.providers.football.replay import ReplayFootballProvider
from app.repositories.database import Database
from app.repositories.models import TelegramSubscriptionRow
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService


async def _service(tmp_path: Path) -> tuple[PredictionService, Database]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'live-semantics.db'}",
        replay_fixture_path=Path("data/replay/live_adversarial.json"),
        simulation_count=1000,
    )
    database = Database(settings)
    await database.create_all()
    provider = CompositeFootballProvider(
        [ReplayFootballProvider(settings.replay_fixture_path)],
        static_ttl=0,
        fixture_ttl=0,
    )
    service = PredictionService(
        settings=settings,
        provider=provider,
        database=database,
        explanations=ExplanationService(None),
        broker=PredictionEventBroker(),
    )
    return service, database


@pytest.mark.asyncio
async def test_extra_time_keeps_regulation_result_settled_as_draw(tmp_path):
    service, database = await _service(tmp_path)
    try:
        prediction = await service.live(
            "demo-match-001",
            generated_at=datetime(2026, 7, 6, 20, 15, 20, tzinfo=UTC),
        )
        assert prediction.status == "EXTRA_TIME"
        assert prediction.outcomes_90_minutes.home_win == 0.0
        assert prediction.outcomes_90_minutes.draw == 1.0
        assert prediction.outcomes_90_minutes.away_win == 0.0
        assert prediction.qualification is not None
        assert prediction.qualification.extra_time == 1.0
        assert "الوقت الإضافي" in prediction.explanation.headline_ar
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_shootout_reports_qualification_not_new_90_minute_forecast(tmp_path):
    service, database = await _service(tmp_path)
    try:
        prediction = await service.live(
            "demo-match-001",
            generated_at=datetime(2026, 7, 6, 20, 35, 5, tzinfo=UTC),
        )
        assert prediction.status == "PENALTIES"
        assert prediction.outcomes_90_minutes.draw == 1.0
        assert prediction.qualification is not None
        assert prediction.qualification.penalties == 1.0
        assert prediction.qualification.home_advance > 0.5
        assert prediction.expected_goals.remaining_home == 0.0
        assert prediction.expected_goals.remaining_away == 0.0
        assert "ركلات الترجيح" in prediction.explanation.headline_ar
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_telegram_subscription_is_persisted_with_hashed_user_id(tmp_path):
    service, database = await _service(tmp_path)
    try:
        await service.subscribe(
            telegram_user_id=123456,
            match_id="demo-match-001",
            kind="probability_delta",
        )
        async for session in database.session():
            row = await session.scalar(select(TelegramSubscriptionRow))
            assert row is not None
            assert row.user_hash != "123456"
            assert len(row.user_hash) == 64
            assert row.match_id == "demo-match-001"
            assert row.kind == "probability_delta"
    finally:
        await database.dispose()
