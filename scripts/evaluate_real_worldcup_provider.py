from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from datetime import datetime, timedelta

from app.core.config import Settings
from app.core.timezones import resolve_timezone
from app.domain.enums import MatchStatus
from app.providers.football.factory import build_football_provider
from app.repositories.database import Database
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _eval_date(settings: Settings):
    value = os.environ.get("WORLD_CUP_EVAL_DATE")
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.now(resolve_timezone(settings.app_timezone)).date()


async def main() -> None:
    settings = Settings(
        app_timezone="Asia/Damascus",
        football_provider="worldcup26",
        football_provider_fallbacks="",
        world_cup_only=True,
        cache_static_ttl_seconds=0,
        cache_fixtures_ttl_seconds=0,
        llm_enabled=False,
        live_polling_enabled=False,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    eval_date = _eval_date(settings)
    provider = build_football_provider(settings)
    database = Database(settings)
    await database.create_all()
    try:
        provider_names = [
            getattr(item, "name", "unknown") for item in getattr(provider, "providers", [provider])
        ]
        statuses = await provider.statuses()
        competitions = await provider.list_competitions()
        all_matches = await provider.list_matches()
        today_matches = await provider.list_matches(date_from=eval_date, date_to=eval_date)
        upcoming_matches = await provider.list_matches(
            date_from=eval_date,
            date_to=eval_date + timedelta(days=7),
        )
        prediction_candidates = [
            match
            for match in [*today_matches, *upcoming_matches]
            if match.status in {MatchStatus.SCHEDULED, MatchStatus.PRE_MATCH}
        ]
        if not today_matches:
            raise AssertionError(f"no World Cup matches returned for {eval_date.isoformat()}")
        if not prediction_candidates:
            raise AssertionError("no non-finished match available for sample prediction")

        service = PredictionService(
            settings=settings,
            provider=provider,
            database=database,
            explanations=ExplanationService(None),
            broker=PredictionEventBroker(),
        )
        prediction = await service.pre_match(prediction_candidates[0].id)
        probabilities = prediction.outcomes_90_minutes
        probability_values = [
            probabilities.home_win,
            probabilities.draw,
            probabilities.away_win,
        ]

        today_labels = [
            f"{match.home_team.name_ar or match.home_team.name} vs "
            f"{match.away_team.name_ar or match.away_team.name}"
            for match in today_matches
        ]
        passed = (
            provider_names == ["worldcup26"]
            and statuses
            and statuses[0]["provider"] == "worldcup26"
            and statuses[0]["healthy"] is True
            and len(competitions) == 1
            and competitions[0].name_ar == "كأس العالم"
            and len(all_matches) == 104
            and len(today_matches) >= 2
            and all(match.id.startswith("worldcup26:game:") for match in today_matches)
            and all(match.competition.name_ar == "كأس العالم" for match in today_matches)
            and all(match.home_team.provider_ids.get("worldcup26") for match in today_matches)
            and all(match.away_team.provider_ids.get("worldcup26") for match in today_matches)
            and all(match.home_team.country_code for match in today_matches)
            and all(match.away_team.country_code for match in today_matches)
            and "المغرب vs الأرجنتين" not in today_labels
            and all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in probability_values)
            and abs(sum(probability_values) - 1.0) <= 1e-8
        )
        report = {
            "passed": passed,
            "eval_date": eval_date.isoformat(),
            "providers": provider_names,
            "statuses": statuses,
            "competitions": [item.model_dump(mode="json") for item in competitions],
            "match_count_total": len(all_matches),
            "today_count": len(today_matches),
            "upcoming_7_day_count": len(upcoming_matches),
            "today_matches": [
                {
                    "id": match.id,
                    "label": label,
                    "kickoff": match.kickoff.isoformat(),
                    "status": match.status.value,
                    "stage": match.stage.value,
                    "home_provider_id": match.home_team.provider_ids.get("worldcup26"),
                    "away_provider_id": match.away_team.provider_ids.get("worldcup26"),
                    "home_country_code": match.home_team.country_code,
                    "away_country_code": match.away_team.country_code,
                }
                for match, label in zip(today_matches, today_labels, strict=True)
            ],
            "sample_prediction": {
                "match_id": prediction.match_id,
                "label": (
                    f"{prediction.home_team.name_ar or prediction.home_team.name} vs "
                    f"{prediction.away_team.name_ar or prediction.away_team.name}"
                ),
                "outcomes_90_minutes": prediction.outcomes_90_minutes.model_dump(),
                "qualification": (
                    prediction.qualification.model_dump() if prediction.qualification else None
                ),
                "data_quality": prediction.data_quality.model_dump(),
                "model": prediction.model.model_dump(),
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not passed:
            raise SystemExit(1)
    finally:
        for item in getattr(provider, "providers", [provider]):
            close = getattr(item, "close", None)
            if close:
                await close()
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
