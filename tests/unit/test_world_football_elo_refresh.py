from scripts.refresh_world_football_elo import build_profiles, parse_world_elo_tsv


def test_parse_world_elo_tsv_and_build_profiles_with_explicit_mapping():
    ratings = parse_world_elo_tsv(
        "\n".join(
            [
                "1\t1\tES\t2159\t1",
                "2\t2\tAR\t2151\t1",
                "bad\trow",
            ]
        )
    )

    profiles = build_profiles(ratings, {"ARG": "AR", "ESP": "ES"})

    assert profiles["arg"]["elo"] == 2151
    assert profiles["esp"]["elo"] == 2159
    assert profiles["arg"]["attack"] > 1.0
    assert profiles["arg"]["defence"] < 1.0
    assert profiles["arg"]["source"] == "world_football_elo"
