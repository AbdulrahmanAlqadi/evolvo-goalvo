from __future__ import annotations

import argparse
from pathlib import Path

import httpx

SOURCES = {
    "statsbomb_competitions": "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json",
    "openfootball_worldcup_2026": "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("data/raw") / f"{args.source}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=30,
        follow_redirects=False,
        headers={"User-Agent": "ArabicFootballForecastAgent/0.1"},
    ) as client:
        response = client.get(SOURCES[args.source])
        response.raise_for_status()
        if len(response.content) > 50_000_000:
            raise SystemExit("download exceeds configured safety limit")
        output.write_bytes(response.content)
    print(f"saved {output}. Review and comply with the source license/data agreement before use.")


if __name__ == "__main__":
    main()
