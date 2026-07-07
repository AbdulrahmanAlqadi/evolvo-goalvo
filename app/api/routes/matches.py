from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request

from app.core.security import require_api_key
from app.core.timezones import resolve_timezone
from app.domain.enums import MatchStatus

router = APIRouter(prefix="/api/v1", tags=["matches"], dependencies=[Depends(require_api_key)])

_PREMATCH_STATUSES = {MatchStatus.SCHEDULED, MatchStatus.PRE_MATCH}
_HIDDEN_LIST_STATUSES = {MatchStatus.FINISHED, MatchStatus.POSTPONED, MatchStatus.CANCELLED}


def _app_now(request: Request) -> datetime:
    settings = getattr(request.app.state, "settings", None)
    timezone_name = getattr(settings, "app_timezone", "UTC")
    return datetime.now(resolve_timezone(timezone_name))


@router.get("/competitions")
async def competitions(request: Request):
    return [
        item.model_dump(mode="json")
        for item in await request.app.state.football_provider.list_competitions()
    ]


@router.get("/matches")
async def matches(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    items = await request.app.state.football_provider.list_matches(
        date_from=date_from, date_to=date_to, status=status
    )
    return {
        "items": [item.model_dump(mode="json") for item in items[offset : offset + limit]],
        "offset": offset,
        "limit": limit,
        "total": len(items),
    }


@router.get("/matches/today")
async def today_matches(request: Request):
    today = _app_now(request).date()
    items = await request.app.state.football_provider.list_matches(date_from=today, date_to=today)
    items = [item for item in items if item.status not in _HIDDEN_LIST_STATUSES]
    return [item.model_dump(mode="json") for item in items]


@router.get("/matches/upcoming")
async def upcoming_matches(request: Request, days: int = Query(7, ge=1, le=30)):
    now = _app_now(request)
    start = now.date()
    items = await request.app.state.football_provider.list_matches(
        date_from=start, date_to=start + timedelta(days=days)
    )
    items = [
        item
        for item in items
        if item.status in _PREMATCH_STATUSES and item.kickoff.astimezone(UTC) >= now
    ]
    return [item.model_dump(mode="json") for item in items]


@router.get("/matches/live")
async def live_matches(request: Request):
    return [
        item.model_dump(mode="json")
        for item in await request.app.state.football_provider.get_live_matches()
    ]


@router.get("/matches/{match_id}")
async def get_match(match_id: str, request: Request):
    return (await request.app.state.football_provider.get_match(match_id)).model_dump(mode="json")


@router.get("/matches/{match_id}/events")
async def get_events(match_id: str, request: Request):
    return [
        item.model_dump(mode="json")
        for item in await request.app.state.football_provider.get_match_events(match_id)
    ]


@router.get("/matches/{match_id}/statistics")
async def get_statistics(match_id: str, request: Request):
    result = await request.app.state.football_provider.get_match_statistics(match_id)
    return result.model_dump(mode="json") if result else None
