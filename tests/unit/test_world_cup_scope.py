from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.domain.entities import Competition, Match, ProviderCapabilities, Score, Team
from app.domain.enums import MatchStage, MatchStatus
from app.providers.football.world_cup_scope import WorldCupFootballProvider


def _match(match_id: str, competition: Competition, home: Team, away: Team) -> Match:
    return Match(
        id=match_id,
        competition=competition,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 7, 6, 18, 0, tzinfo=UTC),
        status=MatchStatus.PRE_MATCH,
        stage=MatchStage.GROUP,
        neutral_venue=True,
        score=Score(),
    )


class MixedCompetitionProvider:
    name = "mixed"
    capabilities = ProviderCapabilities(fixtures=True, live_events=True)

    def __init__(self) -> None:
        self.world_cup = Competition(
            id="mixed:competition:wc-2026",
            name="FIFA World Cup 2026",
            season="2026",
            provider_ids={"mixed": "wc-2026"},
        )
        self.club_world_cup = Competition(
            id="mixed:competition:club-wc",
            name="FIFA Club World Cup",
            season="2026",
            provider_ids={"mixed": "club-wc"},
        )
        self.matches = {
            "wc-match": _match(
                "wc-match",
                self.world_cup,
                Team(id="mixed:team:1", name="Portugal", country_code="POR"),
                Team(id="mixed:team:2", name="Spain", country_code="ESP"),
            ),
            "club-match": _match(
                "club-match",
                self.club_world_cup,
                Team(id="club:1", name="AV Alta FC"),
                Team(id="club:2", name="Charlotte Independence"),
            ),
        }

    async def list_competitions(self):
        return [self.world_cup, self.club_world_cup]

    async def list_matches(self, **_kwargs):
        return list(self.matches.values())

    async def get_match(self, match_id):
        return self.matches[match_id]

    async def get_live_matches(self):
        return list(self.matches.values())

    async def get_match_events(self, _match_id):
        return []

    async def get_match_statistics(self, _match_id):
        return None

    async def get_lineups(self, _match_id):
        return []

    async def get_team(self, team_id):
        return Team(id=team_id, name=team_id)

    async def get_team_squad(self, _team_id):
        return []

    async def get_player_availability(self, _match_id):
        return []

    async def get_injuries(self, _match_id):
        return []

    async def get_standings(self, _competition_id):
        return []

    async def get_odds(self, _match_id):
        return []

    async def get_provider_coverage(self):
        return self.capabilities

    async def healthcheck(self):
        return True

    async def statuses(self):
        return [{"provider": self.name, "healthy": True}]


def _settings() -> Settings:
    return Settings(
        world_cup_only=True,
        world_cup_competition_ids="mixed:wc-2026,wc-2026",
        world_cup_competition_aliases="FIFA World Cup,World Cup",
        team_localization_path="configs/team_localization_ar.json",
    )


@pytest.mark.asyncio
async def test_world_cup_scope_filters_non_world_cup_and_localizes_teams():
    provider = WorldCupFootballProvider(MixedCompetitionProvider(), _settings())

    competitions = await provider.list_competitions()
    assert [competition.id for competition in competitions] == ["mixed:competition:wc-2026"]
    assert competitions[0].name_ar == "كأس العالم"

    matches = await provider.list_matches()
    assert [match.id for match in matches] == ["wc-match"]
    assert matches[0].home_team.name_ar == "البرتغال"
    assert matches[0].away_team.name_ar == "إسبانيا"

    live_matches = await provider.get_live_matches()
    assert [match.id for match in live_matches] == ["wc-match"]


@pytest.mark.asyncio
async def test_world_cup_scope_rejects_direct_non_world_cup_match_access():
    provider = WorldCupFootballProvider(MixedCompetitionProvider(), _settings())

    with pytest.raises(KeyError):
        await provider.get_match("club-match")
