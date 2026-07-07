from app.core.config import Settings
from app.providers.llm.gemini import GeminiProvider
from app.providers.llm.openai_compatible import OpenAICompatibleProvider
from app.providers.llm.router import LLMRouter


def build_llm_router(settings: Settings) -> LLMRouter | None:
    if not settings.llm_enabled:
        return None
    providers = []
    if settings.llm_provider == "gemini":
        providers.append(GeminiProvider(settings))
    if settings.llm_provider == "openai_compatible":
        providers.append(OpenAICompatibleProvider(settings))
    for name in [
        item.strip() for item in settings.llm_fallback_providers.split(",") if item.strip()
    ]:
        if name == "gemini" and all(provider.name != "gemini" for provider in providers):
            providers.append(GeminiProvider(settings))
        if name == "openai_compatible" and all(
            provider.name != "openai_compatible" for provider in providers
        ):
            providers.append(OpenAICompatibleProvider(settings))
    return LLMRouter(providers) if providers else None
