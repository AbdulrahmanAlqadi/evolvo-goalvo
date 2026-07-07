from fastapi import APIRouter, Depends, Request

from app.core.security import require_api_key

router = APIRouter(
    prefix="/api/v1/providers", tags=["providers"], dependencies=[Depends(require_api_key)]
)


@router.get("/status")
async def provider_status(request: Request) -> list[dict]:
    return await request.app.state.football_provider.statuses()
