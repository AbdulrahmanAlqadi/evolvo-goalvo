from datetime import UTC, datetime

from app.domain.entities import Competition, Match, MatchStatistics, Score, Team
from app.domain.enums import MatchStage, MatchStatus
from app.domain.events import CanonicalMatchState
from app.services.predictions import PredictionService


def test_live_evidence_includes_team_statistics_for_llm_context():
    service = PredictionService.__new__(PredictionService)
    match = Match(
        id="worldcup26:game:94",
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=Team(id="usa", name="United States", name_ar="الولايات المتحدة"),
        away_team=Team(id="bel", name="Belgium", name_ar="بلجيكا"),
        kickoff=datetime(2026, 7, 7, 0, 0, tzinfo=UTC),
        status=MatchStatus.LIVE,
        stage=MatchStage.ROUND_OF_16,
        score=Score(),
    )
    state = CanonicalMatchState()
    statistics = MatchStatistics(
        match_id=match.id,
        captured_at=datetime(2026, 7, 7, 0, 10, tzinfo=UTC),
        possession_home=33.8,
        possession_away=66.2,
        shots_home=0,
        shots_away=7,
        shots_on_target_home=0,
        shots_on_target_away=3,
        passes_home=26,
        passes_away=39,
        pass_accuracy_home=88,
        pass_accuracy_away=82,
        corners_home=0,
        corners_away=1,
        fouls_home=1,
        fouls_away=0,
        yellow_cards_home=0,
        yellow_cards_away=0,
        offsides_home=0,
        offsides_away=1,
        saves_home=2,
        saves_away=0,
    )

    evidence = service._live_evidence(match, state, statistics, minute=10)

    stats_evidence = next(item for item in evidence if item.code == "LIVE_TEAM_STATS")
    assert stats_evidence.direction == "AWAY"
    assert "66.2%" in stats_evidence.description_ar
    assert "التسديدات" in stats_evidence.description_ar
    assert "على المرمى" in stats_evidence.description_ar
    assert "التمريرات" in stats_evidence.description_ar
    assert "دقة التمرير" in stats_evidence.description_ar
    assert "الركنيات" in stats_evidence.description_ar
    assert "البطاقات الصفراء" in stats_evidence.description_ar
    assert "التسلل" in stats_evidence.description_ar
    assert "تصديات الحارس" in stats_evidence.description_ar
