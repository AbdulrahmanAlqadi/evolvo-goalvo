from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from app.core.config import Settings
from app.domain.entities import Competition, Match, ProviderCapabilities, Score, Team
from app.domain.enums import MatchStage, MatchStatus
from app.providers.football.world_cup_scope import WorldCupFootballProvider
from app.telegram.keyboards import matches_page


class MixedProvider:
    name = "mixed_eval"
    capabilities = ProviderCapabilities(fixtures=True, live_events=True)

    def __init__(self) -> None:
        world_cup = Competition(
            id="mixed:wc",
            name="FIFA World Cup 2026",
            season="2026",
            provider_ids={"mixed_eval": "wc-2026"},
        )
        league = Competition(
            id="mixed:league",
            name="American USL League One",
            season="2026",
            provider_ids={"mixed_eval": "usl-1"},
        )
        kickoff = datetime(2026, 7, 6, 18, 0, tzinfo=UTC)
        self.matches = {
            "wc": Match(
                id="wc",
                competition=world_cup,
                home_team=Team(id="por", name="Portugal", country_code="POR"),
                away_team=Team(id="esp", name="Spain", country_code="ESP"),
                kickoff=kickoff,
                status=MatchStatus.PRE_MATCH,
                stage=MatchStage.GROUP,
                score=Score(),
            ),
            "league": Match(
                id="league",
                competition=league,
                home_team=Team(id="av-alta", name="AV Alta FC"),
                away_team=Team(id="charlotte", name="Charlotte Independence"),
                kickoff=kickoff,
                status=MatchStatus.PRE_MATCH,
                stage=MatchStage.OTHER,
                score=Score(),
            ),
        }

    async def list_competitions(self):
        return [match.competition for match in self.matches.values()]

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


async def main() -> None:
    settings = Settings(
        world_cup_only=True,
        world_cup_competition_ids="mixed_eval:wc-2026,wc-2026",
        world_cup_competition_aliases="FIFA World Cup,World Cup",
        team_localization_path="configs/team_localization_ar.json",
    )
    provider = WorldCupFootballProvider(MixedProvider(), settings)
    matches = await provider.list_matches()
    label = matches_page(matches, scope="today", page=0).inline_keyboard[0][0].text
    rejected_non_world_cup = False
    try:
        await provider.get_match("league")
    except KeyError:
        rejected_non_world_cup = True

    report = {
        "passed": len(matches) == 1
        and matches[0].competition.name_ar == "كأس العالم"
        and label == "البرتغال vs إسبانيا"
        and rejected_non_world_cup,
        "served_match_ids": [match.id for match in matches],
        "telegram_label": label,
        "world_cup_name_ar": matches[0].competition.name_ar if matches else None,
        "rejected_non_world_cup": rejected_non_world_cup,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
