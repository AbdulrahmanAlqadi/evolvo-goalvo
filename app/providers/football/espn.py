from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.domain.entities import MatchStatistics, ProviderCapabilities
from app.providers.football.base import ProviderUnavailable
from app.providers.football.http import SafeHttpProvider


class EspnFootballProvider(SafeHttpProvider):
    name = "espn"
    capabilities = ProviderCapabilities(
        fixtures=False,
        live_events=False,
        lineups=False,
        injuries=False,
        statistics=True,
        expected_goals=False,
        odds=False,
        standings=False,
        squads=False,
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            base_url=settings.espn_api_base_url,
            per_minute=60,
            per_day=5000,
        )
        self.match_ids = self._load_mapping(settings.espn_match_id_map)

    @staticmethod
    def _load_mapping(raw: str) -> dict[str, str]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("ESPN_MATCH_ID_MAP must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("ESPN_MATCH_ID_MAP must be a JSON object")
        return {str(key): str(value) for key, value in payload.items()}

    @staticmethod
    def _number(value: Any) -> float | None:
        text = str(value or "").strip().replace("%", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None

    @classmethod
    def _int_stat(cls, values: dict[str, Any], key: str) -> int | None:
        number = cls._number(values.get(key))
        return int(number) if number is not None else None

    @classmethod
    def _float_stat(cls, values: dict[str, Any], key: str) -> float | None:
        return cls._number(values.get(key))

    @classmethod
    def _percent_stat(cls, values: dict[str, Any], key: str) -> float | None:
        number = cls._number(values.get(key))
        if number is not None and 0 <= number <= 1:
            return number * 100
        return number

    async def _summary(self, event_id: str) -> dict[str, Any]:
        return await self._request_json(
            "get_match_statistics",
            "GET",
            "/apis/site/v2/sports/soccer/fifa.world/summary",
            params={"event": event_id},
        )

    async def get_match_statistics(self, match_id: str) -> MatchStatistics | None:
        event_id = self.match_ids.get(match_id)
        if not event_id:
            raise ProviderUnavailable(f"no ESPN event mapping for {match_id}")
        payload = await self._summary(event_id)
        teams = payload.get("boxscore", {}).get("teams") or []
        if len(teams) < 2:
            return None
        home_stats = {
            item.get("name"): item.get("displayValue")
            for item in teams[0].get("statistics", [])
            if isinstance(item, dict)
        }
        away_stats = {
            item.get("name"): item.get("displayValue")
            for item in teams[1].get("statistics", [])
            if isinstance(item, dict)
        }
        return MatchStatistics(
            match_id=match_id,
            captured_at=datetime.now(UTC),
            possession_home=self._float_stat(home_stats, "possessionPct"),
            possession_away=self._float_stat(away_stats, "possessionPct"),
            shots_home=self._int_stat(home_stats, "totalShots"),
            shots_away=self._int_stat(away_stats, "totalShots"),
            shots_on_target_home=self._int_stat(home_stats, "shotsOnTarget"),
            shots_on_target_away=self._int_stat(away_stats, "shotsOnTarget"),
            passes_home=self._int_stat(home_stats, "totalPasses"),
            passes_away=self._int_stat(away_stats, "totalPasses"),
            pass_accuracy_home=self._percent_stat(home_stats, "passPct"),
            pass_accuracy_away=self._percent_stat(away_stats, "passPct"),
            corners_home=self._int_stat(home_stats, "wonCorners"),
            corners_away=self._int_stat(away_stats, "wonCorners"),
            fouls_home=self._int_stat(home_stats, "foulsCommitted"),
            fouls_away=self._int_stat(away_stats, "foulsCommitted"),
            yellow_cards_home=self._int_stat(home_stats, "yellowCards"),
            yellow_cards_away=self._int_stat(away_stats, "yellowCards"),
            red_cards_home=self._int_stat(home_stats, "redCards") or 0,
            red_cards_away=self._int_stat(away_stats, "redCards") or 0,
            offsides_home=self._int_stat(home_stats, "offsides"),
            offsides_away=self._int_stat(away_stats, "offsides"),
            saves_home=self._int_stat(home_stats, "saves"),
            saves_away=self._int_stat(away_stats, "saves"),
        )

    async def healthcheck(self) -> bool:
        if not self.match_ids:
            return False
        try:
            await self._summary(next(iter(self.match_ids.values())))
        except Exception:
            return False
        return True
