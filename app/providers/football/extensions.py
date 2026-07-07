"""Extension contracts for licensed providers.

Sportmonks, Sportradar, Stats Perform/Opta and other commercial adapters should implement
``FootballProvider`` and declare precise capability flags. They are intentionally not represented
as working integrations without credentials, schemas and contractual permission.
"""

from app.providers.football.base import FootballProvider

__all__ = ["FootballProvider"]
