from pydantic import BaseModel


class ProviderStatus(BaseModel):
    provider: str
    healthy: bool
    capabilities: dict[str, bool]
    error: str | None = None
