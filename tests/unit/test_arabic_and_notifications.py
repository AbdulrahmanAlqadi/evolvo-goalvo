from datetime import UTC, datetime, timedelta

from app.domain.entities import Competition, Match, Score, Team
from app.domain.enums import MatchStage, MatchStatus
from app.schemas.predictions import (
    CompetitionRef,
    DataQuality,
    EvidenceItem,
    ExpectedGoals,
    Explanation,
    ModelMetadata,
    Outcome90,
    PredictionResponse,
    Qualification,
    Scoreline,
    TeamRef,
    Uncertainty,
)
from app.services.arabic import format_number, percent, telegram_prediction_text
from app.telegram.formatting import split_message
from app.telegram.keyboards import matches_page
from app.telegram.notifications import should_notify_change


def test_arabic_digits():
    assert format_number(2026, arabic_digits=True) == "٢٠٢٦"
    assert percent(0.48, arabic_digits=True) == "٤٨%"


def test_message_splitting():
    chunks = split_message("a\n" * 5000, limit=100)
    assert all(len(chunk) <= 100 or chunk == "a" for chunk in chunks)


def test_match_button_uses_arabic_names_with_vs_separator():
    match = Match(
        id="wc-match",
        competition=Competition(id="wc-2026", name="FIFA World Cup", season="2026"),
        home_team=Team(id="por", name="Portugal", name_ar="البرتغال"),
        away_team=Team(id="esp", name="Spain", name_ar="إسبانيا"),
        kickoff=datetime(2026, 7, 6, 18, 0, tzinfo=UTC),
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.GROUP,
        score=Score(),
    )

    keyboard = matches_page([match], scope="today", page=0)

    assert keyboard.inline_keyboard[0][0].text == "البرتغال vs إسبانيا"


def test_telegram_prediction_text_is_clean_narrative_without_math_blocks():
    generated_at = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
    prediction = PredictionResponse(
        prediction_id="prediction-1",
        match_id="worldcup26:game:94",
        competition=CompetitionRef(
            id="worldcup26:competition:2026",
            name="FIFA World Cup",
            season="2026",
        ),
        home_team=TeamRef(id="worldcup26:team:8", name="Switzerland", name_ar="سويسرا"),
        away_team=TeamRef(id="worldcup26:team:44", name="Colombia", name_ar="كولومبيا"),
        status="PRE_MATCH",
        generated_at=generated_at,
        data_as_of=generated_at,
        data_freshness_seconds=0,
        outcomes_90_minutes=Outcome90(home_win=0.43, draw=0.32, away_win=0.25),
        qualification=Qualification(
            home_advance=0.59,
            away_advance=0.41,
            extra_time=0.32,
            penalties=0.12,
        ),
        expected_goals=ExpectedGoals(home=1.35, away=0.92),
        likely_scorelines=[
            Scoreline(home_goals=1, away_goals=0, probability=0.18),
            Scoreline(home_goals=2, away_goals=1, probability=0.14),
            Scoreline(home_goals=1, away_goals=1, probability=0.13),
            Scoreline(home_goals=2, away_goals=0, probability=0.11),
        ],
        uncertainty=Uncertainty(level="medium", reason_codes=["LINEUPS_NOT_CONFIRMED"]),
        evidence=[
            EvidenceItem(
                code="TEAM_STRENGTH",
                direction="HOME",
                importance=0.35,
                description_ar="تقييم القوة من النتائج المتاحة.",
            )
        ],
        data_quality=DataQuality(completeness=0.7, freshness_seconds=0, warnings=[]),
        model=ModelMetadata(
            ensemble_version="prematch-ensemble-v1",
            calibration_version="identity-v1",
            component_versions={"elo": "elo-v1"},
        ),
        provenance=[{"provider": "worldcup26", "stage": "ROUND_OF_16"}],
        explanation=Explanation(
            headline_ar="النتيجة الأرجح بعد 90 دقيقة: سويسرا",
            summary_ar="سويسرا أقرب للفوز.",
            key_factors_ar=["تقييم القوة من النتائج المتاحة."],
            uncertainty_ar="درجة عدم اليقين: متوسطة.",
            data_warning_ar=None,
            generated_by="llm",
        ),
        disclaimer_ar="هذه احتمالات تقديرية وليست ضماناً.",
    )

    text = telegram_prediction_text(prediction, arabic_digits=False)

    assert "لماذا هذا التوقع (تحليل الذكاء الاصطناعي):" in text
    assert "سويسرا أقرب للفوز." in text
    assert "النتيجة المحتملة: 2-1 لصالح سويسرا" in text
    assert "احتمالات الفوز:" in text
    assert "• سويسرا: 43%" in text
    assert "• التعادل: 32%" in text
    assert "• كولومبيا: 25%" in text
    assert "احتمالات الأهداف:" in text
    assert "• أكثر من 2.5 هدف:" in text
    assert "• تسجيل المنتخبين:" in text
    assert "توقع الأهداف:" not in text
    assert "أقرب النتائج الدقيقة:" not in text
    assert "درجة عدم اليقين" not in text
    assert "احتمال التأهل" not in text


def test_notification_threshold_and_cooldown():
    now = datetime.now(UTC)
    assert should_notify_change(
        {"home_win": 0.4, "draw": 0.3, "away_win": 0.3},
        {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
        threshold=0.08,
        last_notified_at=None,
        now=now,
        cooldown_seconds=300,
    )
    assert not should_notify_change(
        {"home_win": 0.4, "draw": 0.3, "away_win": 0.3},
        {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
        threshold=0.08,
        last_notified_at=now - timedelta(seconds=10),
        now=now,
        cooldown_seconds=300,
    )
