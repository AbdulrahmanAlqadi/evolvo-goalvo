import pytest

from app.providers.football.base import ProviderUnavailable
from app.providers.football.composite import CompositeFootballProvider
from app.providers.football.mock import MockFootballProvider


class FailingProvider(MockFootballProvider):
    name = "failing"

    async def list_matches(self, **kwargs):
        raise ProviderUnavailable("down")

    async def healthcheck(self):
        return False


@pytest.mark.asyncio
async def test_composite_falls_back_to_supported_provider():
    provider = CompositeFootballProvider([FailingProvider(), MockFootballProvider()])
    matches = await provider.list_matches()
    assert matches[0].id == "demo-match-001"
