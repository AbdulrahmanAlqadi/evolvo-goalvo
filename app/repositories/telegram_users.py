from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import TelegramUserRow


class TelegramUserRepository:
    async def touch(self, session: AsyncSession, *, user_hash: str) -> None:
        now = datetime.now(UTC)
        row = await session.get(TelegramUserRow, user_hash)
        if row is None:
            session.add(
                TelegramUserRow(
                    user_hash=user_hash,
                    first_seen_at=now,
                    last_seen_at=now,
                    interaction_count=1,
                )
            )
        else:
            row.last_seen_at = now
            row.interaction_count += 1
            row.active = True

    async def active_count(self, session: AsyncSession) -> int:
        statement = select(func.count()).select_from(TelegramUserRow).where(
            TelegramUserRow.active.is_(True)
        )
        return int(await session.scalar(statement) or 0)
