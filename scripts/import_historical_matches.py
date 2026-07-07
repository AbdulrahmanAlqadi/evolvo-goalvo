from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

REQUIRED = {
    "played_at",
    "competition",
    "stage",
    "home_team_id",
    "away_team_id",
    "home_goals",
    "away_goals",
    "neutral",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path", type=Path, nargs="?", default=Path("data/processed/historical_matches.csv")
    )
    args = parser.parse_args()
    with args.path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"missing columns: {sorted(missing)}")
        rows = list(reader)
    seen = set()
    for row in rows:
        datetime.fromisoformat(row["played_at"].replace("Z", "+00:00"))
        if row["home_team_id"] == row["away_team_id"]:
            raise SystemExit("home and away teams must differ")
        key = (row["played_at"], row["home_team_id"], row["away_team_id"])
        if key in seen:
            raise SystemExit(f"duplicate canonical match key: {key}")
        seen.add(key)
    print(f"validated {len(rows)} chronological historical matches from {args.path}")


if __name__ == "__main__":
    main()
