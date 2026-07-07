from __future__ import annotations

import json
from datetime import UTC, date, datetime

from app.core.config import Settings
from app.domain.entities import (
    Competition,
    Match,
    ProviderCapabilities,
    Score,
    Team,
)
from app.domain.enums import MatchStage, MatchStatus
from app.providers.football.http import SafeHttpProvider


class TheSportsDbProvider(SafeHttpProvider):
    name = "thesportsdb"
    capabilities = ProviderCapabilities(
        fixtures=True,
        live_events=False,
        lineups=False,
        injuries=False,
        statistics=False,
        standings=False,
        squads=True,
    )

    def __init__(self, settings: Settings) -> None:
        base = f"{settings.thesportsdb_base_url.rstrip('/')}/{settings.thesportsdb_key}"
        super().__init__(settings, base_url=base, per_minute=30, per_day=10000)
        self.team_map = (
            json.loads(settings.thesportsdb_team_mapping_path.read_text(encoding="utf-8"))
            if settings.thesportsdb_team_mapping_path.exists()
            else {}
        )

    def _event(self, item: dict) -> Match:
        kickoff_raw = f"{item.get('dateEvent')}T{item.get('strTime') or '00:00:00'}+00:00"
        try:
            kickoff = datetime.fromisoformat(kickoff_raw).astimezone(UTC)
        except ValueError:
            kickoff = datetime.now(UTC)
        status = (
            MatchStatus.FINISHED if item.get("intHomeScore") is not None else MatchStatus.PRE_MATCH
        )
        return Match(
            id=f"thesportsdb:event:{item['idEvent']}",
            competition=Competition(
                id=f"thesportsdb:league:{item.get('idLeague')}",
                name=item.get("strLeague") or "Unknown",
                season=item.get("strSeason") or "unknown",
                provider_ids={self.name: str(item.get("idLeague"))},
            ),
            home_team=Team(
                id=f"thesportsdb:team:{item.get('idHomeTeam')}",
                name=item.get("strHomeTeam") or "Unknown",
                provider_ids={self.name: str(item.get("idHomeTeam"))},
            ),
            away_team=Team(
                id=f"thesportsdb:team:{item.get('idAwayTeam')}",
                name=item.get("strAwayTeam") or "Unknown",
                provider_ids={self.name: str(item.get("idAwayTeam"))},
            ),
            kickoff=kickoff,
            status=status,
            stage=MatchStage.OTHER,
            neutral_venue=True,
            venue=item.get("strVenue"),
            score=Score(
                home=int(item.get("intHomeScore") or 0), away=int(item.get("intAwayScore") or 0)
            ),
        )

    async def list_competitions(self):
        return []

    async def list_matches(self, *, competition_id=None, date_from=None, date_to=None, status=None):
        target = date_from or date.today()
        payload = await self._request_json(
            "list_matches",
            "GET",
            "/eventsday.php",
            params={"d": target.isoformat(), "s": "Soccer"},
        )
        return [self._event(item) for item in payload.get("events") or []]

    async def get_match(self, match_id: str):
        payload = await self._request_json(
            "get_match", "GET", "/lookupevent.php", params={"id": match_id.rsplit(":", 1)[-1]}
        )
        return self._event(payload["events"][0])

    async def get_live_matches(self):
        return []

    async def get_match_events(self, match_id):
        return []

    async def get_match_statistics(self, match_id):
        return None

    async def get_lineups(self, match_id):
        return []

    async def get_team(self, team_id):
        payload = await self._request_json(
            "get_team", "GET", "/lookupteam.php", params={"id": team_id.rsplit(":", 1)[-1]}
        )
        raw = payload["teams"][0]
        return Team(id=team_id, name=raw["strTeam"], provider_ids={self.name: str(raw["idTeam"])})

    async def get_team_squad(self, team_id):
        provider_id = team_id.rsplit(":", 1)[-1]
        mapping = self.team_map.get(f"worldcup26:{provider_id}") or self.team_map.get(team_id)
        thesportsdb_id = (
            mapping.get("thesportsdb_id")
            if isinstance(mapping, dict)
            else provider_id
            if team_id.startswith("thesportsdb:team:")
            else None
        )
        if not thesportsdb_id:
            return []
        payload = await self._request_json(
            "get_team_squad",
            "GET",
            "/lookup_all_players.php",
            params={"id": thesportsdb_id},
        )
        players = payload.get("player") or []
        if not isinstance(players, list):
            return []
        return [
            {
                "provider": self.name,
                "team_id": team_id,
                "player_id": f"thesportsdb:player:{item.get('idPlayer')}",
                "name": item.get("strPlayer"),
                "position": item.get("strPosition"),
                "nationality": item.get("strNationality"),
                "source": "thesportsdb_squad",
            }
            for item in players
            if isinstance(item, dict) and item.get("idPlayer") and item.get("strPlayer")
        ]

    async def get_player_availability(self, match_id):
        return []

    async def get_injuries(self, match_id):
        return []

    async def get_standings(self, competition_id):
        return []

    async def get_odds(self, match_id):
        return []

    async def get_provider_coverage(self):
        return self.capabilities

    async def healthcheck(self):
        return True
