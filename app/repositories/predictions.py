from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import MatchRow, PredictionRow


class PredictionRepository:
    async def save(self, session: AsyncSession, row: PredictionRow) -> None:
        session.add(row)
        await session.commit()

    async def latest(self, session: AsyncSession, match_id: str) -> PredictionRow | None:
        statement = (
            select(PredictionRow)
            .where(PredictionRow.match_id == match_id)
            .order_by(desc(PredictionRow.generated_at))
            .limit(1)
        )
        return await session.scalar(statement)

    async def history(
        self, session: AsyncSession, match_id: str, limit: int = 50
    ) -> list[PredictionRow]:
        statement = (
            select(PredictionRow)
            .where(PredictionRow.match_id == match_id)
            .order_by(desc(PredictionRow.generated_at))
            .limit(limit)
        )
        return list((await session.scalars(statement)).all())

    async def finished_archive(
        self, session: AsyncSession, limit: int = 20
    ) -> list[tuple[PredictionRow, MatchRow]]:
        statement = (
            select(PredictionRow, MatchRow)
            .join(MatchRow, MatchRow.id == PredictionRow.match_id)
            .where(MatchRow.status == "FINISHED")
            .where(MatchRow.id.like("worldcup26:game:%"))
            .where(PredictionRow.kind == "pre_match")
            .order_by(desc(MatchRow.kickoff), desc(PredictionRow.generated_at))
            .limit(limit)
        )
        return list((await session.execute(statement)).all())
