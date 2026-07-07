import json

import pytest

from app.core.config import Settings
from app.providers.football.thesportsdb import TheSportsDbProvider


@pytest.mark.asyncio
async def test_thesportsdb_squad_uses_explicit_worldcup_mapping(tmp_path, monkeypatch):
    mapping_path = tmp_path / "thesportsdb_team_map.json"
    mapping_path.write_text(
        json.dumps({"worldcup26:41": {"thesportsdb_id": "133908"}}),
        encoding="utf-8",
    )
    provider = TheSportsDbProvider(
        Settings(
            football_provider="thesportsdb",
            thesportsdb_team_mapping_path=mapping_path,
        )
    )

    async def fake_request_json(operation, method, path, *, params=None):
        assert operation == "get_team_squad"
        assert path == "/lookup_all_players.php"
        assert params == {"id": "133908"}
        return {
            "player": [
                {
                    "idPlayer": "34145961",
                    "strPlayer": "Bruno Fernandes",
                    "strPosition": "Central Midfield",
                    "strNationality": "Portugal",
                }
            ]
        }

    monkeypatch.setattr(provider, "_request_json", fake_request_json)

    players = await provider.get_team_squad("worldcup26:team:41")

    assert players == [
        {
            "provider": "thesportsdb",
            "team_id": "worldcup26:team:41",
            "player_id": "thesportsdb:player:34145961",
            "name": "Bruno Fernandes",
            "position": "Central Midfield",
            "nationality": "Portugal",
            "source": "thesportsdb_squad",
        }
    ]
