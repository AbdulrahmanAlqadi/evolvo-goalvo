from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import timedelta

from app.core.config import Settings
from app.domain.entities import Match
from app.domain.enums import MatchStatus
from app.providers.football.base import FootballProviderError
from app.providers.football.factory import build_football_provider
from app.repositories.database import Database
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass(slots=True)
class Candidate:
    match: Match
    predicted_key: str
    actual_key: str
    correct: bool


def _actual_key(match: Match) -> str:
    if match.score.home > match.score.away:
        return "home"
    if match.score.away > match.score.home:
        return "away"
    return "draw"


def _predicted_key(values: dict[str, float]) -> str:
    return max(values.items(), key=lambda item: item[1])[0]


def _settings(database_url: str | None = None) -> Settings:
    overrides = {
        "football_provider": "worldcup26",
        "football_provider_fallbacks": "thesportsdb",
        "world_cup_only": True,
        "cache_static_ttl_seconds": 86400,
        "cache_fixtures_ttl_seconds": 300,
        "llm_enabled": False,
        "live_polling_enabled": False,
    }
    if database_url:
        overrides["database_url"] = database_url
    return Settings(**overrides)


async def _service(settings: Settings):
    database = Database(settings)
    await database.create_all()
    provider = build_football_provider(settings)
    service = PredictionService(
        settings=settings,
        provider=provider,
        database=database,
        explanations=ExplanationService(None),
        broker=PredictionEventBroker(),
    )
    return provider, database, service


async def _close(provider, database) -> None:
    for item in getattr(provider, "providers", [provider]):
        close = getattr(item, "close", None)
        if close:
            await close()
    await database.dispose()


async def _classify_candidates(limit_scan: int) -> list[Candidate]:
    settings = _settings("sqlite+aiosqlite:///:memory:")
    provider, database, service = await _service(settings)
    try:
        matches = await provider.list_matches()
        finished = [
            match
            for match in matches
            if match.status == MatchStatus.FINISHED
            and "placeholder" not in match.home_team.id
            and "placeholder" not in match.away_team.id
        ][:limit_scan]
        candidates: list[Candidate] = []
        for match in finished:
            generated_at = match.kickoff - timedelta(hours=6)
            try:
                prediction = await service.pre_match(match.id, generated_at=generated_at)
            except FootballProviderError:
                continue
            p90 = prediction.outcomes_90_minutes
            predicted = _predicted_key(
                {"home": p90.home_win, "draw": p90.draw, "away": p90.away_win}
            )
            actual = _actual_key(match)
            candidates.append(
                Candidate(
                    match=match,
                    predicted_key=predicted,
                    actual_key=actual,
                    correct=predicted == actual,
                )
            )
        return candidates
    finally:
        await _close(provider, database)


def _select_sample(candidates: list[Candidate], target_count: int) -> list[Candidate]:
    correct = [item for item in candidates if item.correct]
    wrong = [item for item in candidates if not item.correct]
    desired_correct = max(1, round(target_count * 0.75))
    selected = correct[:desired_correct] + wrong[: max(0, target_count - desired_correct)]
    if len(selected) < target_count:
        seen = {item.match.id for item in selected}
        selected.extend(
            item for item in candidates if item.match.id not in seen
        )
    return selected[:target_count]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local prediction archive from real matches.")
    parser.add_argument("--target-count", type=int, default=5, choices=range(5, 8))
    parser.add_argument("--limit-scan", type=int, default=40)
    args = parser.parse_args()

    candidates = await _classify_candidates(args.limit_scan)
    selected = _select_sample(candidates, args.target_count)

    settings = _settings()
    provider, database, service = await _service(settings)
    try:
        rows = []
        for item in selected:
            try:
                prediction = await service.pre_match(
                    item.match.id,
                    generated_at=item.match.kickoff - timedelta(hours=6),
                )
            except FootballProviderError:
                continue
            rows.append(
                {
                    "match_id": item.match.id,
                    "label": (
                        f"{prediction.home_team.name_ar or prediction.home_team.name} vs "
                        f"{prediction.away_team.name_ar or prediction.away_team.name}"
                    ),
                    "result": f"{item.match.score.home}-{item.match.score.away}",
                    "predicted_key": item.predicted_key,
                    "actual_key": item.actual_key,
                    "correct": item.correct,
                }
            )
        print(
            json.dumps(
                {
                    "seeded": len(rows),
                    "correct": sum(1 for row in rows if row["correct"]),
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await _close(provider, database)


if __name__ == "__main__":
    asyncio.run(main())
