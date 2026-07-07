from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(request: Request) -> dict:
    provider_ok = await request.app.state.football_provider.healthcheck()
    database_ok = True
    try:
        async with request.app.state.database.engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
    except Exception:
        database_ok = False
    status = "ready" if provider_ok and database_ok else "degraded"
    return {
        "status": status,
        "database": database_ok,
        "football_provider": provider_ok,
        "llm_required": False,
    }
