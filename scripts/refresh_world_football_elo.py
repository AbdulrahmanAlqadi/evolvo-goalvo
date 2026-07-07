from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SOURCE_URL = "https://eloratings.net/World.tsv"
DEFAULT_CODE_MAP_PATH = Path("configs/world_football_elo_code_map.json")
DEFAULT_OUTPUT_PATH = Path("configs/team_profiles.json")


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_world_elo_tsv(text: str) -> dict[str, int]:
    ratings: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 4:
            continue
        code = parts[2].strip().upper()
        if len(code) != 2:
            continue
        try:
            rating = int(parts[3])
        except ValueError:
            continue
        ratings[code] = rating
    return ratings


def profile_from_elo(rating: int) -> dict[str, Any]:
    strength = (rating - 1500.0) / 3600.0
    return {
        "elo": rating,
        "attack": round(_clip(1.0 + strength, 0.75, 1.25), 3),
        "defence": round(_clip(1.0 - strength, 0.75, 1.25), 3),
        "source": "world_football_elo",
    }


def build_profiles(
    ratings_by_elo_code: dict[str, int], fifa_to_elo_code: dict[str, str]
) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for fifa_code, elo_code in sorted(fifa_to_elo_code.items()):
        rating = ratings_by_elo_code.get(elo_code.upper())
        if rating is None:
            missing.append(f"{fifa_code}:{elo_code}")
            continue
        profiles[fifa_code.lower()] = profile_from_elo(rating)
    if missing:
        raise ValueError(f"missing World Football Elo ratings for mapped teams: {missing}")
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh configured team-strength priors from World Football Elo."
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--code-map", type=Path, default=DEFAULT_CODE_MAP_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    code_map = json.loads(args.code_map.read_text(encoding="utf-8"))
    response = httpx.get(args.source_url, timeout=30)
    response.raise_for_status()
    ratings = parse_world_elo_tsv(response.text)
    profiles = build_profiles(ratings, code_map)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "source_url": args.source_url,
                "teams_written": len(profiles),
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
