from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.domain.entities import Competition, Match, Score, Team
from app.domain.enums import MatchStage, MatchStatus
from app.schemas.predictions import (
    CompetitionRef,
    DataQuality,
    ExpectedGoals,
    Explanation,
    ModelMetadata,
    Outcome90,
    PredictionResponse,
    TeamRef,
    Uncertainty,
)
from app.telegram.handlers import _archive_text, _list_matches, _prediction_for_match, callback
from app.telegram.keyboards import main_menu, match_actions, matches_page


def _context(*, data: str, update_id: int = 1):
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    settings = Settings(telegram_rate_limit_per_minute=1000)
    provider = SimpleNamespace()
    service = SimpleNamespace(
        subscribe=AsyncMock(),
        record_telegram_user=AsyncMock(),
        telegram_user_count=AsyncMock(return_value=3),
        prediction_archive=AsyncMock(return_value=[]),
    )
    bot_data = {
        "settings": settings,
        "provider": provider,
        "prediction_service": service,
    }
    context = SimpleNamespace(application=SimpleNamespace(bot_data=bot_data))
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
        update_id=update_id,
    )
    return update, context, query, service


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_main_menu_callbacks_are_unique():
    callbacks = _callbacks(main_menu())

    assert len(callbacks) == len(set(callbacks))
    assert callbacks == [
        "matches:prematch:0",
        "matches:live_forecast:0",
        "predictions:archive:0",
    ]


def test_match_action_callbacks_are_unique():
    callbacks = _callbacks(match_actions("demo-match-001"))

    assert len(callbacks) == len(set(callbacks))


def test_matches_page_can_route_directly_to_promised_action():
    match = Match(
        id="demo-match-001",
        competition=Competition(id="wc-2026", name="FIFA World Cup", season="2026"),
        home_team=Team(id="por", name="Portugal", name_ar="البرتغال"),
        away_team=Team(id="esp", name="Spain", name_ar="إسبانيا"),
        kickoff="2026-07-06T18:00:00Z",
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.GROUP,
        score=Score(),
    )

    predict_button = matches_page([match], scope="prematch", page=0, action="predict")
    explain_button = matches_page([match], scope="explain", page=0, action="explain")
    live_button = matches_page([match], scope="live_forecast", page=0, action="live")

    assert predict_button.inline_keyboard[0][0].callback_data == "predict:demo-match-001"
    assert explain_button.inline_keyboard[0][0].callback_data == "explain:demo-match-001"
    assert live_button.inline_keyboard[0][0].callback_data == "live:demo-match-001"


def test_archive_text_uses_country_names_not_home_away_labels():
    prediction = PredictionResponse(
        prediction_id="p1",
        match_id="worldcup26:game:1",
        competition=CompetitionRef(id="wc", name="FIFA World Cup", season="2026"),
        home_team=TeamRef(id="mex", name="Mexico", name_ar="المكسيك"),
        away_team=TeamRef(id="rsa", name="South Africa", name_ar="جنوب أفريقيا"),
        status="PRE_MATCH",
        generated_at="2026-07-01T10:00:00Z",
        data_as_of="2026-07-01T10:00:00Z",
        data_freshness_seconds=0,
        outcomes_90_minutes=Outcome90(home_win=0.5, draw=0.3, away_win=0.2),
        expected_goals=ExpectedGoals(home=1.4, away=0.8),
        likely_scorelines=[],
        uncertainty=Uncertainty(level="medium", reason_codes=[]),
        evidence=[],
        data_quality=DataQuality(completeness=0.8, freshness_seconds=0),
        model=ModelMetadata(
            ensemble_version="v1",
            calibration_version="v1",
            component_versions={},
        ),
        provenance=[],
        explanation=Explanation(
            headline_ar="التوقع الأقرب: المكسيك",
            summary_ar="المكسيك أقرب.",
            key_factors_ar=[],
            uncertainty_ar="",
        ),
        disclaimer_ar="",
    )

    text = _archive_text(
        [
            {
                "prediction": prediction,
                "home_score": 2,
                "away_score": 0,
                "predicted_key": "home",
                "actual_key": "home",
                "correct": True,
            }
        ]
    )

    assert "التوقع: المكسيك" in text
    assert "فوز صاحب الأرض" not in text
    assert "فوز الضيف" not in text


@pytest.mark.asyncio
async def test_match_lists_hide_finished_games_from_today_and_upcoming():
    future_kickoff = datetime.now(UTC) + timedelta(days=1)
    finished_kickoff = datetime.now(UTC) - timedelta(hours=1)
    now_match = Match(
        id="future",
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=Team(id="arg", name="Argentina"),
        away_team=Team(id="mar", name="Morocco"),
        kickoff=future_kickoff,
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.GROUP,
        score=Score(),
    )
    finished_match = Match(
        id="finished",
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=Team(id="mex", name="Mexico"),
        away_team=Team(id="rsa", name="South Africa"),
        kickoff=finished_kickoff,
        status=MatchStatus.FINISHED,
        stage=MatchStage.GROUP,
        score=Score(home=2, away=0),
    )

    class Provider:
        async def list_matches(self, **_kwargs):
            return [finished_match, now_match]

    settings = Settings(app_timezone="UTC")

    today = await _list_matches(Provider(), "today", settings)
    upcoming = await _list_matches(Provider(), "upcoming", settings)

    assert [match.id for match in today] == ["future"]
    assert [match.id for match in upcoming] == ["future"]


@pytest.mark.asyncio
async def test_live_list_includes_matches_starting_soon():
    soon_kickoff = datetime.now(UTC) + timedelta(minutes=10)
    later_kickoff = datetime.now(UTC) + timedelta(hours=2)
    soon_match = Match(
        id="soon",
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=Team(id="usa", name="United States"),
        away_team=Team(id="bel", name="Belgium"),
        kickoff=soon_kickoff,
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.ROUND_OF_16,
        score=Score(),
    )
    later_match = Match(
        id="later",
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=Team(id="arg", name="Argentina"),
        away_team=Team(id="egy", name="Egypt"),
        kickoff=later_kickoff,
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.ROUND_OF_16,
        score=Score(),
    )

    class Provider:
        async def get_live_matches(self):
            return []

        async def list_matches(self, **_kwargs):
            return [soon_match, later_match]

    settings = Settings(app_timezone="UTC")

    live = await _list_matches(Provider(), "live_forecast", settings)

    assert [match.id for match in live] == ["soon"]


@pytest.mark.asyncio
async def test_live_button_uses_prematch_prediction_before_actual_kickoff():
    future_match = Match(
        id="soon",
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=Team(id="usa", name="United States"),
        away_team=Team(id="bel", name="Belgium"),
        kickoff=datetime.now(UTC) + timedelta(minutes=10),
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.ROUND_OF_16,
        score=Score(),
    )
    provider = SimpleNamespace(get_match=AsyncMock(return_value=future_match))
    service = SimpleNamespace(
        live=AsyncMock(return_value="live"),
        pre_match=AsyncMock(return_value="prematch"),
    )

    result = await _prediction_for_match(service, provider, "soon", force_live=True)

    assert result == "prematch"
    service.pre_match.assert_awaited_once_with("soon")
    service.live.assert_not_awaited()


@pytest.mark.asyncio
async def test_methodology_callback_is_acknowledged_and_duplicate_safe():
    update, context, query, _service = _context(data="methodology", update_id=77)
    await callback(update, context)
    await callback(update, context)

    assert query.answer.await_count == 2
    assert query.edit_message_text.await_count == 1
    assert "نموذج اللغة" in query.edit_message_text.await_args.args[0]


@pytest.mark.asyncio
async def test_archive_callback_is_wide_menu_entry_and_handled():
    update, context, query, service = _context(data="predictions:archive:0", update_id=79)
    await callback(update, context)

    service.prediction_archive.assert_awaited_once_with(limit=7)
    assert "لا توجد توقعات منتهية" in query.edit_message_text.await_args.args[0]


@pytest.mark.asyncio
async def test_subscription_callback_persists_preference():
    update, context, query, service = _context(data="subscribe_delta:demo-match-001", update_id=78)
    await callback(update, context)

    service.subscribe.assert_awaited_once_with(
        telegram_user_id=123,
        match_id="demo-match-001",
        kind="probability_delta",
    )
    assert (123, "demo-match-001", "probability_delta") in context.application.bot_data[
        "delivery_subscriptions"
    ]
    assert "تم حفظ" in query.edit_message_text.await_args.args[0]
