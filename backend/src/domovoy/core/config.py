"""Настройки приложения. Все значения берутся из переменных окружения или файла .env."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["stub", "ollama_cloud", "ollama_local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Домовой Кузя"
    log_level: str = "INFO"

    # Мок-режим: вход без подписи MAX, эмулятор чата, демо-данные.
    mock_max: bool = True
    seed_demo: bool = True

    database_url: str = "postgresql+asyncpg://domovoy:domovoy@localhost:5432/domovoy"
    rabbit_url: str = "amqp://guest:guest@localhost:5672/"

    s3_endpoint: str = "localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_bucket: str = "domovoy"
    s3_secure: bool = False

    # MAX
    max_bot_token: SecretStr = SecretStr("")
    max_api_url: str = "https://platform-api2.max.ru"
    max_bot_username: str = "domovoy_kuzya_bot"
    max_poll_timeout: int = 30
    init_data_ttl_seconds: int = 24 * 3600

    # LLM
    llm_provider: LlmProvider = "stub"
    ollama_cloud_url: str = "https://ollama.com"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_local_url: str = "http://localhost:11434"
    llm_model: str = "gpt-oss:120b"
    llm_temperature: float = 0.3
    llm_timeout_seconds: float = 60.0

    embedding_dim: int = 256

    # Механики
    default_vote_threshold_pct: int = 15
    min_votes_needed: int = 3
    event_reminder_minutes: int = 120
    moderation_strikes_limit: int = 3
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_max_files: int = 5

    # Дополнительные MCP-серверы для агента в формате JSON:
    # [{"name": "weather", "transport": "streamable_http", "url": "http://..."}]
    extra_mcp_servers: str = "[]"
    internal_mcp_url: str = "http://localhost:8765/mcp"
    internal_mcp_enabled: bool = True

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    public_app_url: str = "http://localhost:8080"

    @property
    def bot_token(self) -> str:
        return self.max_bot_token.get_secret_value()

    @property
    def has_max_token(self) -> bool:
        return bool(self.bot_token)

    @property
    def psycopg_url(self) -> str:
        """URL для чекпоинтера LangGraph (psycopg без драйвера asyncpg)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
