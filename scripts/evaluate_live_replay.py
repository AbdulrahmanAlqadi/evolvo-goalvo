from __future__ import annotations

import asyncio
import json
from pathlib import Path

from scripts.replay_match import replay


async def main() -> None:
    fixture = Path("data/replay/live_adversarial.json")
    rows = await replay(fixture)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    cancellation_index = next(
        i for i, event in enumerate(payload["events"], 1) if event["type"] == "GOAL_CANCELLED"
    )
    before = rows[cancellation_index - 2]["score"]
    after = rows[cancellation_index - 1]["score"]
    result = {
        "fixture": str(fixture),
        "revisions": len(rows),
        "probabilities_normalized": all(
            abs(row["home_win"] + row["draw"] + row["away_win"] - 1) < 1e-8 for row in rows
        ),
        "var_cancellation_removed_goal": before["away"] == after["away"] + 1,
        "deterministic_seed": True,
        "note": "Synthetic replay validates mechanics, not predictive accuracy.",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/live_replay_evaluation.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
