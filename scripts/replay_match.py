from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.core.config import Settings
from app.providers.football.factory import build_football_provider
from app.repositories.database import Database
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService


async def replay(fixture: Path) -> list[dict]:
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///./data/replay_runtime.db",
        football_provider="replay",
        football_provider_fallbacks="",
        replay_fixture_path=fixture,
        llm_enabled=False,
        simulation_count=3000,
    )
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
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for index, event in enumerate(payload.get("events", []), start=1):
        prediction = await service.live(
            payload["match"]["id"],
            generated_at=datetime.fromisoformat(event["received_at"].replace("Z", "+00:00")),
            event_limit=index,
        )
        rows.append(
            {
                "event_index": index,
                "event_type": event["type"],
                "minute": event["minute"],
                "score": prediction.provenance[0]["score"],
                "home_win": prediction.outcomes_90_minutes.home_win,
                "draw": prediction.outcomes_90_minutes.draw,
                "away_win": prediction.outcomes_90_minutes.away_win,
                "warnings": prediction.data_quality.warnings,
            }
        )
    await database.dispose()
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/replay_result.json"))
    args = parser.parse_args()
    rows = await replay(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    print(f"saved {len(rows)} revisions to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
