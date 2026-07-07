from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.domain.entities import (
    Competition,
    Match,
    MatchEvent,
    MatchStatistics,
    Provenance,
    ProviderCapabilities,
    Score,
    Team,
)
from app.domain.enums import EventType, MatchStage, MatchStatus, TeamSide
from app.providers.football.http import SafeHttpProvider

_STATUS_MAP = {
    "NS": MatchStatus.PRE_MATCH,
    "TBD": MatchStatus.SCHEDULED,
    "1H": MatchStatus.LIVE,
    "HT": MatchStatus.HALF_TIME,
    "2H": MatchStatus.LIVE,
    "ET": MatchStatus.EXTRA_TIME,
    "BT": MatchStatus.EXTRA_TIME,
    "P": MatchStatus.PENALTIES,
    "FT": MatchStatus.FINISHED,
    "AET": MatchStatus.FINISHED,
    "PEN": MatchStatus.FINISHED,
    "PST": MatchStatus.POSTPONED,
    "CANC": MatchStatus.CANCELLED,
}


class ApiFootballProvider(SafeHttpProvider):
    name = "api_football"
    capabilities = ProviderCapabilities(
        fixtures=True,
        live_events=True,
        lineups=True,
        injuries=True,
        statistics=True,
        expected_goals=False,
        odds=True,
        standings=True,
        squads=True,
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            base_url=settings.api_football_base_url,
            headers={"x-apisports-key": settings.api_football_key},
            per_minute=settings.api_football_minute_budget,
            per_day=settings.api_football_daily_budget,
        )

    @staticmethod
    def _stage(value: str | None) -> MatchStage:
        text = (value or "").lower()
        if "group" in text:
            return MatchStage.GROUP
        if "final" in text and "semi" not in text and "quarter" not in text:
            return MatchStage.FINAL
        if "semi" in text:
            return MatchStage.SEMI_FINAL
        if "quarter" in text:
            return MatchStage.QUARTER_FINAL
        if "round of 16" in text:
            return MatchStage.ROUND_OF_16
        return MatchStage.OTHER

    def _canonical_match(self, item: dict[str, Any]) -> Match:
        fixture = item["fixture"]
        league = item["league"]
        teams = item["teams"]
        goals = item.get("goals") or {}
        timestamp = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")).astimezone(UTC)
        observed = datetime.now(UTC)
        competition = Competition(
            id=f"api-football:league:{league['id']}:{league['season']}",
            name=league["name"],
            season=str(league["season"]),
            provider_ids={self.name: str(league["id"])},
        )
        home = Team(
            id=f"api-football:team:{teams['home']['id']}",
            name=teams["home"]["name"],
            provider_ids={self.name: str(teams["home"]["id"])},
        )
        away = Team(
            id=f"api-football:team:{teams['away']['id']}",
            name=teams["away"]["name"],
            provider_ids={self.name: str(teams["away"]["id"])},
        )
        return Match(
            id=f"api-football:fixture:{fixture['id']}",
            competition=competition,
            home_team=home,
            away_team=away,
            kickoff=timestamp,
            status=_STATUS_MAP.get(fixture["status"]["short"], MatchStatus.SCHEDULED),
            stage=self._stage(league.get("round")),
            neutral_venue=bool(fixture.get("venue")),
            venue=(fixture.get("venue") or {}).get("name"),
            minute=fixture["status"].get("elapsed"),
            period=fixture["status"].get("long"),
            score=Score(home=goals.get("home") or 0, away=goals.get("away") or 0),
            updated_at=observed,
            provenance=[
                Provenance(
                    provider=self.name, provider_entity_id=str(fixture["id"]), observed_at=observed
                )
            ],
        )

    async def list_competitions(self) -> list[Competition]:
        payload = await self._request_json(
            "list_competitions", "GET", "/leagues", params={"current": "true"}
        )
        result: list[Competition] = []
        for item in payload.get("response", []):
            league = item.get("league", {})
            for season in item.get("seasons", []):
                if season.get("current"):
                    result.append(
                        Competition(
                            id=f"api-football:league:{league.get('id')}:{season.get('year')}",
                            name=league.get("name", "Unknown"),
                            season=str(season.get("year")),
                            provider_ids={self.name: str(league.get("id"))},
                        )
                    )
        return result

    async def list_matches(
        self, *, competition_id=None, date_from=None, date_to=None, status=None
    ) -> list[Match]:
        params: dict[str, Any] = {
            "league": self.settings.api_football_competition_id,
            "season": self.settings.api_football_season,
        }
        if date_from:
            params["from"] = date_from.isoformat()
        if date_to:
            params["to"] = date_to.isoformat()
        if status:
            params["status"] = status
        payload = await self._request_json("list_matches", "GET", "/fixtures", params=params)
        return [self._canonical_match(item) for item in payload.get("response", [])]

    async def get_match(self, match_id: str) -> Match:
        fixture_id = match_id.rsplit(":", 1)[-1]
        payload = await self._request_json(
            "get_match", "GET", "/fixtures", params={"id": fixture_id}
        )
        return self._canonical_match(payload["response"][0])

    async def get_live_matches(self) -> list[Match]:
        payload = await self._request_json(
            "get_live_matches", "GET", "/fixtures", params={"live": "all"}
        )
        return [self._canonical_match(item) for item in payload.get("response", [])]

    async def get_match_events(self, match_id: str) -> list[MatchEvent]:
        fixture_id = match_id.rsplit(":", 1)[-1]
        payload = await self._request_json(
            "get_match_events", "GET", "/fixtures/events", params={"fixture": fixture_id}
        )
        result: list[MatchEvent] = []
        for index, item in enumerate(payload.get("response", [])):
            detail = str(item.get("detail", ""))
            event_type = EventType.OTHER
            if item.get("type") == "Goal":
                event_type = EventType.GOAL
            elif item.get("type") == "Card" and "Red" in detail:
                event_type = EventType.RED_CARD
            elif item.get("type") == "subst":
                event_type = EventType.SUBSTITUTION
            team = item.get("team") or {}
            match = await self.get_match(match_id)
            side = (
                TeamSide.HOME
                if str(team.get("id")) == match.home_team.provider_ids.get(self.name)
                else TeamSide.AWAY
            )
            provider_event_id = str(
                item.get("id") or f"{fixture_id}:{index}:{item.get('time', {}).get('elapsed')}"
            )
            minute = int((item.get("time") or {}).get("elapsed") or 0)
            observed = datetime.now(UTC)
            result.append(
                MatchEvent(
                    id=f"{self.name}:{provider_event_id}",
                    match_id=match_id,
                    provider=self.name,
                    provider_event_id=provider_event_id,
                    type=event_type,
                    side=side,
                    minute=minute,
                    occurred_at=observed,
                    received_at=observed,
                    payload={"detail": detail},
                )
            )
        return result

    async def get_match_statistics(self, match_id: str) -> MatchStatistics | None:
        fixture_id = match_id.rsplit(":", 1)[-1]
        payload = await self._request_json(
            "get_match_statistics", "GET", "/fixtures/statistics", params={"fixture": fixture_id}
        )
        teams = payload.get("response", [])
        if len(teams) < 2:
            return None

        def value(team: dict, key: str):
            for stat in team.get("statistics", []):
                if stat.get("type") == key:
                    raw = stat.get("value")
                    if isinstance(raw, str) and raw.endswith("%"):
                        return float(raw[:-1])
                    return raw
            return None

        return MatchStatistics(
            match_id=match_id,
            captured_at=datetime.now(UTC),
            possession_home=value(teams[0], "Ball Possession"),
            possession_away=value(teams[1], "Ball Possession"),
            shots_home=value(teams[0], "Total Shots"),
            shots_away=value(teams[1], "Total Shots"),
            shots_on_target_home=value(teams[0], "Shots on Goal"),
            shots_on_target_away=value(teams[1], "Shots on Goal"),
            corners_home=value(teams[0], "Corner Kicks"),
            corners_away=value(teams[1], "Corner Kicks"),
            red_cards_home=value(teams[0], "Red Cards") or 0,
            red_cards_away=value(teams[1], "Red Cards") or 0,
        )

    async def get_lineups(self, match_id: str) -> list[dict]:
        fixture_id = match_id.rsplit(":", 1)[-1]
        return (
            await self._request_json(
                "get_lineups", "GET", "/fixtures/lineups", params={"fixture": fixture_id}
            )
        ).get("response", [])

    async def get_team(self, team_id: str) -> Team:
        provider_id = team_id.rsplit(":", 1)[-1]
        payload = await self._request_json("get_team", "GET", "/teams", params={"id": provider_id})
        item = payload["response"][0]["team"]
        return Team(id=team_id, name=item["name"], provider_ids={self.name: str(item["id"])})

    async def get_team_squad(self, team_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_team_squad",
                "GET",
                "/players/squads",
                params={"team": team_id.rsplit(":", 1)[-1]},
            )
        ).get("response", [])

    async def get_player_availability(self, match_id: str) -> list[dict]:
        return await self.get_injuries(match_id)

    async def get_injuries(self, match_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_injuries", "GET", "/injuries", params={"fixture": match_id.rsplit(":", 1)[-1]}
            )
        ).get("response", [])

    async def get_standings(self, competition_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_standings",
                "GET",
                "/standings",
                params={
                    "league": self.settings.api_football_competition_id,
                    "season": self.settings.api_football_season,
                },
            )
        ).get("response", [])

    async def get_odds(self, match_id: str) -> list[dict]:
        return (
            await self._request_json(
                "get_odds", "GET", "/odds", params={"fixture": match_id.rsplit(":", 1)[-1]}
            )
        ).get("response", [])

    async def get_provider_coverage(self) -> ProviderCapabilities:
        return self.capabilities

    async def healthcheck(self) -> bool:
        if not self.settings.api_football_key:
            return False
        try:
            await self._request_json("healthcheck", "GET", "/status")
            return True
        except Exception:
            return False
