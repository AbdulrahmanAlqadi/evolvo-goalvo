from __future__ import annotations

import asyncio
import json

from app.core.config import get_settings
from app.providers.football.factory import build_football_provider


async def main() -> None:
    provider = build_football_provider(get_settings())
    print(json.dumps(await provider.statuses(), indent=2))
    matches = await provider.list_matches()
    print(
        json.dumps(
            {"matches": len(matches), "first_match": matches[0].id if matches else None}, indent=2
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
