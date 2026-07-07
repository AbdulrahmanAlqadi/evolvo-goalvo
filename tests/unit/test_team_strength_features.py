from datetime import UTC, datetime

from app.domain.entities import Competition, Match, Score, Team
from app.domain.enums import MatchStage, MatchStatus
from app.features.team_strength import build_team_strength_profiles


def _match(
    match_id: str,
    *,
    home: Team,
    away: Team,
    kickoff: datetime,
    status: MatchStatus = MatchStatus.FINISHED,
    score: Score | None = None,
) -> Match:
    return Match(
        id=match_id,
        competition=Competition(id="wc", name="FIFA World Cup", season="2026"),
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        status=status,
        stage=MatchStage.GROUP,
        neutral_venue=True,
        score=score or Score(home=0, away=0),
        updated_at=kickoff,
    )


def test_team_strength_uses_available_past_results_and_rejects_future_results():
    portugal = Team(id="worldcup26:team:41", name="Portugal", country_code="POR")
    spain = Team(id="worldcup26:team:29", name="Spain", country_code="ESP")
    croatia = Team(id="worldcup26:team:46", name="Croatia", country_code="CRO")
    austria = Team(id="worldcup26:team:39", name="Austria", country_code="AUT")
    target = _match(
        "target",
        home=portugal,
        away=spain,
        kickoff=datetime(2026, 7, 6, 14, 0, tzinfo=UTC),
        status=MatchStatus.PRE_MATCH,
    )
    past_portugal = _match(
        "past-por",
        home=portugal,
        away=croatia,
        kickoff=datetime(2026, 7, 2, 19, 0, tzinfo=UTC),
        score=Score(home=2, away=1),
    )
    past_spain = _match(
        "past-esp",
        home=spain,
        away=austria,
        kickoff=datetime(2026, 7, 2, 12, 0, tzinfo=UTC),
        score=Score(home=3, away=0),
    )
    future_spain = _match(
        "future-esp",
        home=spain,
        away=croatia,
        kickoff=datetime(2026, 7, 6, 13, 0, tzinfo=UTC),
        score=Score(home=9, away=0),
    )

    home, away, history = build_team_strength_profiles(
        target,
        historical_matches=[past_portugal, past_spain, future_spain],
        prediction_time=datetime(2026, 7, 6, 11, 0, tzinfo=UTC),
        configured_profiles={},
    )

    assert [match.id for match in history] == ["past-esp", "past-por"]
    assert home.matches_played == 1
    assert away.matches_played == 1
    assert away.goal_difference == 3
    assert away.goals_for == 3
    assert away.goals_for != 12
    assert home.source == "tournament_results"
    assert away.source == "tournament_results"
    assert home.opponent_average_elo is not None
    assert away.opponent_average_elo is not None
    assert home.opponent_adjusted_form is not None
    assert away.opponent_adjusted_form is not None
    assert home.rest_days is not None
    assert away.rest_days is not None
    assert home.fatigue_penalty == 0.02
    assert away.fatigue_penalty == 0.0
