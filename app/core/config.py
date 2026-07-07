from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Arabic Football Forecast Agent"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_timezone: str = "UTC"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    api_auth_enabled: bool = True
    api_key: str = "change-me"
    expose_debug_details: bool = False
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    cors_origins: str = ""
    max_request_bytes: int = Field(default=1_048_576, ge=1024)
    api_rate_limit_requests: int = Field(default=120, ge=1, le=100_000)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)

    football_provider: str = "worldcup26"
    football_provider_fallbacks: str = "api_football,football_data_org,thesportsdb,replay,mock"
    football_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    football_max_retries: int = Field(default=2, ge=0, le=5)
    football_allowed_hosts: str = (
        "v3.football.api-sports.io,api.football-data.org,www.thesportsdb.com,worldcup26.ir"
    )
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_daily_budget: int = Field(default=100, ge=0)
    api_football_minute_budget: int = Field(default=10, ge=0)
    api_football_competition_id: int = 1
    api_football_season: int = 2026
    football_data_org_key: str = ""
    football_data_org_base_url: str = "https://api.football-data.org/v4"
    thesportsdb_key: str = "3"
    thesportsdb_base_url: str = "https://www.thesportsdb.com/api/v1/json"
    thesportsdb_team_mapping_path: Path = Path("./configs/thesportsdb_team_map.json")
    worldcup26_base_url: str = "https://worldcup26.ir"
    world_cup_only: bool = True
    world_cup_competition_ids: str = (
        "worldcup26:2026,worldcup26:competition:2026,replay:wc-2026,wc-2026,"
        "api_football:1,football_data_org:WC,thesportsdb:4429"
    )
    world_cup_competition_aliases: str = (
        "FIFA World Cup,World Cup,Coupe du Monde,Copa Mundial,"
        "كأس العالم,كاس العالم,كأس العالم لكرة القدم"
    )
    team_localization_path: Path = Path("./configs/team_localization_ar.json")

    cache_enabled: bool = True
    cache_static_ttl_seconds: int = Field(default=86400, ge=0)
    cache_fixtures_ttl_seconds: int = Field(default=300, ge=0)
    cache_live_ttl_seconds: int = Field(default=15, ge=0)

    live_polling_enabled: bool = False
    live_poll_interval_seconds: int = Field(default=30, ge=1)
    live_poll_min_interval_seconds: int = Field(default=15, ge=1)
    live_poll_max_interval_seconds: int = Field(default=120, ge=1)
    live_data_stale_after_seconds: int = Field(default=90, ge=1)
    live_recompute_on_event: bool = True
    live_recompute_on_stats_change: bool = True
    live_notification_min_delta: float = Field(default=0.08, ge=0, le=1)
    live_notification_cooldown_seconds: int = Field(default=300, ge=0)

    prediction_mode: Literal["ensemble", "elo", "poisson"] = "ensemble"
    model_registry_path: Path = Path("./data/models/registry.json")
    prematch_model_version: str = "prematch-ensemble-v1"
    live_model_version: str = "live-simulation-v1"
    calibration_version: str = "identity-v1"
    allow_uncalibrated_fallback: bool = True
    simulation_count: int = Field(default=10000, ge=100, le=1_000_000)
    simulation_seed: int = 2026
    max_score_goals: int = Field(default=10, ge=5, le=20)
    ensemble_elo_weight: float = Field(default=0.35, ge=0)
    ensemble_poisson_weight: float = Field(default=0.45, ge=0)
    ensemble_classifier_weight: float = Field(default=0.20, ge=0)
    dixon_coles_rho: float = Field(default=-0.08, ge=-0.5, le=0.5)
    market_prior_enabled: bool = False
    qualitative_context_enabled: bool = False

    llm_enabled: bool = False
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    llm_fallback_providers: str = "openai,anthropic,openai_compatible"
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=700, ge=64, le=8192)
    gemini_api_key_1: str = ""
    gemini_api_key_2: str = ""
    gemini_api_key_3: str = ""
    gemini_key_selection_strategy: Literal["least_recently_used", "round_robin"] = (
        "least_recently_used"
    )
    gemini_key_cooldown_seconds: int = Field(default=60, ge=1)
    gemini_max_attempts_per_request: int = Field(default=2, ge=1, le=3)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_compatible_api_key: str = ""
    openai_compatible_base_url: str = ""

    telegram_enabled: bool = False
    telegram_mode: Literal["polling", "webhook"] = "polling"
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_user_ids: str = ""
    telegram_admin_user_ids: str = ""
    telegram_notification_min_delta: float = Field(default=0.08, ge=0, le=1)
    telegram_notification_cooldown_seconds: int = Field(default=300, ge=0)
    telegram_rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)

    arabic_digits_enabled: bool = False
    arabic_explanation_style: Literal["concise", "detailed"] = "concise"
    arabic_disclaimer_enabled: bool = True

    replay_mode: bool = False
    replay_fixture_path: Path = Path("./data/replay/sample_match.json")
    mock_clock_enabled: bool = False

    @field_validator("api_key")
    @classmethod
    def reject_empty_api_key_when_enabled(cls, value: str) -> str:
        if not value:
            raise ValueError("API_KEY must not be empty")
        return value

    @model_validator(mode="after")
    def validate_intervals_and_secrets(self) -> Settings:
        if not (
            self.live_poll_min_interval_seconds
            <= self.live_poll_interval_seconds
            <= self.live_poll_max_interval_seconds
        ):
            raise ValueError("live polling interval must be within configured bounds")
        if self.telegram_enabled and not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required when Telegram is enabled")
        if self.app_env == "production" and self.api_auth_enabled and self.api_key == "change-me":
            raise ValueError("default API key is forbidden in production")
        if (
            self.ensemble_elo_weight
            + self.ensemble_poisson_weight
            + self.ensemble_classifier_weight
            <= 0
        ):
            raise ValueError("at least one ensemble weight must be positive")
        return self

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def football_fallback_list(self) -> list[str]:
        return [
            item.strip() for item in self.football_provider_fallbacks.split(",") if item.strip()
        ]

    @property
    def world_cup_competition_id_set(self) -> set[str]:
        return {
            item.strip()
            for item in self.world_cup_competition_ids.split(",")
            if item.strip()
        }

    @property
    def world_cup_competition_alias_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.world_cup_competition_aliases.split(",")
            if item.strip()
        ]

    @property
    def gemini_keys(self) -> list[str]:
        return [
            key
            for key in [self.gemini_api_key_1, self.gemini_api_key_2, self.gemini_api_key_3]
            if key
        ]

    @property
    def telegram_allowed_user_id_set(self) -> set[int]:
        return {
            int(item.strip()) for item in self.telegram_allowed_user_ids.split(",") if item.strip()
        }

    @property
    def telegram_admin_user_id_set(self) -> set[int]:
        return {
            int(item.strip()) for item in self.telegram_admin_user_ids.split(",") if item.strip()
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
