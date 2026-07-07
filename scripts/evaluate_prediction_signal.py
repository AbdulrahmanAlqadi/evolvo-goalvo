from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.providers.football.factory import build_football_provider
from app.repositories.database import Database
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _eval_date():
    value = os.environ.get("WORLD_CUP_EVAL_DATE")
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.now(UTC).date()


async def main() -> None:
    eval_date = _eval_date()
    settings = Settings(
        football_provider="worldcup26",
        football_provider_fallbacks="",
        world_cup_only=True,
        cache_static_ttl_seconds=0,
        cache_fixtures_ttl_seconds=0,
        llm_enabled=False,
        live_polling_enabled=False,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    provider = build_football_provider(settings)
    database = Database(settings)
    await database.create_all()
    try:
        service = PredictionService(
            settings=settings,
            provider=provider,
            database=database,
            explanations=ExplanationService(None),
            broker=PredictionEventBroker(),
        )
        matches = await provider.list_matches(
            date_from=eval_date,
            date_to=eval_date + timedelta(days=7),
        )
        concrete_matches = [
            match
            for match in matches
            if "placeholder" not in match.home_team.id and "placeholder" not in match.away_team.id
        ]
        rows = []
        for match in concrete_matches:
            prediction = await service.pre_match(match.id)
            p90 = prediction.outcomes_90_minutes
            values = [p90.home_win, p90.draw, p90.away_win]
            top_two = sorted(values, reverse=True)[:2]
            qualification_edge = (
                abs(prediction.qualification.home_advance - prediction.qualification.away_advance)
                if prediction.qualification
                else top_two[0] - top_two[1]
            )
            rows.append(
                {
                    "match_id": match.id,
                    "label": (
                        f"{prediction.home_team.name_ar or prediction.home_team.name} vs "
                        f"{prediction.away_team.name_ar or prediction.away_team.name}"
                    ),
                    "kickoff": match.kickoff.isoformat(),
                    "outcomes_90_minutes": p90.model_dump(),
                    "qualification": (
                        prediction.qualification.model_dump()
                        if prediction.qualification
                        else None
                    ),
                    "top_margin_90": top_two[0] - top_two[1],
                    "qualification_edge": qualification_edge,
                    "evidence_codes": [item.code for item in prediction.evidence],
                    "team_strength": prediction.provenance[0].get("team_strength"),
                    "warnings": prediction.data_quality.warnings,
                }
            )

        edges = [row["qualification_edge"] for row in rows]
        required_free_signals = {
            "worldcup26_fixtures_scores",
            "opponent_adjusted_history",
            "tournament_form",
            "rest_days",
            "world_football_elo_prior",
        }
        required_unavailable_signals = {"confirmed_lineups", "market_odds", "xg"}
        free_signal_coverage_ok = all(
            required_free_signals.issubset(
                set((row["team_strength"] or {}).get("free_signals_used") or [])
            )
            and required_unavailable_signals.issubset(
                set((row["team_strength"] or {}).get("free_signals_unavailable") or [])
            )
            for row in rows
        )
        opponent_adjusted_ok = all(
            (row["team_strength"] or {}).get("home_opponent_average_elo") is not None
            and (row["team_strength"] or {}).get("away_opponent_average_elo") is not None
            and (row["team_strength"] or {}).get("home_opponent_adjusted_form") is not None
            and (row["team_strength"] or {}).get("away_opponent_adjusted_form") is not None
            for row in rows
        )
        passed = (
            len(rows) >= 4
            and max(edges, default=0.0) >= 0.15
            and sum(edges) / max(1, len(edges)) >= 0.08
            and any(row["top_margin_90"] >= 0.08 for row in rows)
            and all("TOURNAMENT_FORM" in row["evidence_codes"] for row in rows)
            and free_signal_coverage_ok
            and opponent_adjusted_ok
        )
        report = {
            "passed": passed,
            "eval_date": eval_date.isoformat(),
            "matches_checked": len(rows),
            "max_qualification_edge": max(edges, default=0.0),
            "average_qualification_edge": sum(edges) / max(1, len(edges)),
            "free_signal_coverage_ok": free_signal_coverage_ok,
            "opponent_adjusted_ok": opponent_adjusted_ok,
            "predictions": rows,
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
