from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import TelegramSubscriptionRow


class TelegramSubscriptionRepository:
    async def upsert(
        self,
        session: AsyncSession,
        *,
        user_hash: str,
        match_id: str,
        kind: str,
        threshold: float,
    ) -> TelegramSubscriptionRow:
        row = await session.scalar(
            select(TelegramSubscriptionRow).where(
                TelegramSubscriptionRow.user_hash == user_hash,
                TelegramSubscriptionRow.match_id == match_id,
                TelegramSubscriptionRow.kind == kind,
            )
        )
        if row is None:
            row = TelegramSubscriptionRow(
                user_hash=user_hash,
                match_id=match_id,
                kind=kind,
                threshold=threshold,
                active=True,
            )
            session.add(row)
        else:
            row.threshold = threshold
            row.active = True
        await session.commit()
        await session.refresh(row)
        return row
