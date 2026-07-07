from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.domain.entities import (
    Competition,
    Match,
    MatchEvent,
    MatchStatistics,
    ProviderCapabilities,
    Score,
    Team,
)
from app.domain.enums import MatchStage, MatchStatus
from app.providers.football.http import SafeHttpProvider

_STATUS = {
    "SCHEDULED": MatchStatus.PRE_MATCH,
    "TIMED": MatchStatus.PRE_MATCH,
    "IN_PLAY": MatchStatus.LIVE,
    "PAUSED": MatchStatus.HALF_TIME,
    "FINISHED": MatchStatus.FINISHED,
    "POSTPONED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
}


class FootballDataOrgProvider(SafeHttpProvider):
    name = "football_data_org"
    capabilities = ProviderCapabilities(
        fixtures=True, live_events=True, lineups=True, statistics=False, standings=True, squads=True
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            base_url=settings.football_data_org_base_url,
            headers={"X-Auth-Token": settings.football_data_org_key},
            per_minute=10,
            per_day=10000,
        )

    def _match(self, item: dict) -> Match:
        competition_raw = item["competition"]
        season = item.get("season", {})
        home_raw, away_raw = item["homeTeam"], item["awayTeam"]
        score = item.get("score", {}).get("fullTime") or {}
        stage_raw = item.get("stage", "OTHER")
        stage = (
            MatchStage(stage_raw)
            if stage_raw in MatchStage._value2member_map_
            else MatchStage.OTHER
        )
        return Match(
            id=f"football-data-org:match:{item['id']}",
            competition=Competition(
                id=(
                    f"football-data-org:competition:{competition_raw['id']}:"
                    f"{season.get('startDate', '')[:4]}"
                ),
                name=competition_raw["name"],
                season=season.get("startDate", "")[:4] or "unknown",
                provider_ids={self.name: str(competition_raw["id"])},
            ),
            home_team=Team(
                id=f"football-data-org:team:{home_raw['id']}",
                name=home_raw.get("name") or home_raw.get("shortName") or "Unknown",
                provider_ids={self.name: str(home_raw["id"])},
            ),
            away_team=Team(
                id=f"football-data-org:team:{away_raw['id']}",
                name=away_raw.get("name") or away_raw.get("shortName") or "Unknown",
                provider_ids={self.name: str(away_raw["id"])},
            ),
            kickoff=datetime.fromisoformat(item["utcDate"].replace("Z", "+00:00")).astimezone(UTC),
            status=_STATUS.get(item.get("status"), MatchStatus.SCHEDULED),
            stage=stage,
            neutral_venue=True,
            minute=item.get("minute"),
            score=Score(home=score.get("home") or 0, away=score.get("away") or 0),
            updated_at=datetime.now(UTC),
        )

    async def list_competitions(self) -> list[Competition]:
        payload = await self._request_json("list_competitions", "GET", "/competitions")
        return [
            Competition(
                id=(
                    f"football-data-org:competition:{item['id']}:"
                    f"{item.get('currentSeason', {}).get('startDate', '')[:4]}"
                ),
                name=item["name"],
                season=item.get("currentSeason", {}).get("startDate", "")[:4] or "unknown",
                provider_ids={self.name: str(item["id"])},
            )
            for item in payload.get("competitions", [])
        ]

    async def list_matches(
        self, *, competition_id=None, date_from=None, date_to=None, status=None
    ) -> list[Match]:
        params = {}
        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()
        if status:
            params["status"] = status
        path = (
            "/matches"
            if not competition_id
            else f"/competitions/{competition_id.rsplit(':', 2)[-2]}/matches"
        )
        payload = await self._request_json("list_matches", "GET", path, params=params)
        return [self._match(item) for item in payload.get("matches", [])]

    async def get_match(self, match_id: str) -> Match:
        payload = await self._request_json(
            "get_match", "GET", f"/matches/{match_id.rsplit(':', 1)[-1]}"
        )
        return self._match(payload)

    async def get_live_matches(self) -> list[Match]:
        return await self.list_matches(status="IN_PLAY")

    async def get_match_events(self, match_id: str) -> list[MatchEvent]:
        await self.get_match(match_id)
        # This API has no stable high-granularity event identity contract here.
        return []

    async def get_match_statistics(self, match_id: str) -> MatchStatistics | None:
        return None

    async def get_lineups(self, match_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_lineups", "GET", f"/matches/{match_id.rsplit(':', 1)[-1]}"
            )
        ).get("lineups", [])

    async def get_team(self, team_id: str) -> Team:
        raw = await self._request_json("get_team", "GET", f"/teams/{team_id.rsplit(':', 1)[-1]}")
        return Team(id=team_id, name=raw["name"], provider_ids={self.name: str(raw["id"])})

    async def get_team_squad(self, team_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_team_squad", "GET", f"/teams/{team_id.rsplit(':', 1)[-1]}"
            )
        ).get("squad", [])

    async def get_player_availability(self, match_id: str) -> list[dict]:
        return []

    async def get_injuries(self, match_id: str) -> list[dict]:
        return []

    async def get_standings(self, competition_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_standings",
                "GET",
                f"/competitions/{competition_id.rsplit(':', 2)[-2]}/standings",
            )
        ).get("standings", [])

    async def get_odds(self, match_id: str) -> list[dict]:
        return []

    async def get_provider_coverage(self) -> ProviderCapabilities:
        return self.capabilities

    async def healthcheck(self) -> bool:
        if not self.settings.football_data_org_key:
            return False
        try:
            await self._request_json("healthcheck", "GET", "/competitions")
            return True
        except Exception:
            return False
