from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Match
from app.repositories.models import CompetitionRow, MatchRow, TeamRow


class CatalogRepository:
    async def upsert_match_graph(self, session: AsyncSession, match: Match) -> None:
        await session.merge(
            CompetitionRow(
                id=match.competition.id,
                name=match.competition.name,
                name_ar=match.competition.name_ar,
            )
        )
        for team in (match.home_team, match.away_team):
            await session.merge(
                TeamRow(
                    id=team.id,
                    name=team.name,
                    name_ar=team.name_ar,
                    country_code=team.country_code,
                )
            )
        await session.flush()
        await session.merge(
            MatchRow(
                id=match.id,
                competition_id=match.competition.id,
                season_id=None,
                home_team_id=match.home_team.id,
                away_team_id=match.away_team.id,
                venue_id=None,
                canonical_external_key=match.id,
                kickoff=match.kickoff,
                status=match.status.value,
                stage=match.stage.value,
                neutral_venue=match.neutral_venue,
                score_home=match.score.home,
                score_away=match.score.away,
                minute=match.minute,
                provider_updated_at=match.updated_at,
            )
        )
