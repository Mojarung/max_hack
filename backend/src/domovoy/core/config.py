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
    rabbit_url: str = "amqp://domovoy:domovoy@localhost:5672/"

    s3_endpoint: str = "localhost:9000"
    s3_access_key: str = "domovoy"
    s3_secret_key: SecretStr = SecretStr("domovoy-secret")
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

    # Отправка обращений на ТЕСТОВЫЙ e-mail (модельная интеграция: настоящей УК письмо не уходит).
    # Пусто APPEAL_TEST_EMAIL или SMTP_HOST = обращение только сохраняется в карточке заявки.
    appeal_test_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_ssl: bool = False
    smtp_starttls: bool = False
    smtp_from: str = "Домовой Кузя <kuzya@domovoy.local>"

    # Дополнительные MCP-серверы для агента в формате JSON:
    # [{"name": "weather", "transport": "streamable_http", "url": "http://..."}]
    extra_mcp_servers: str = "[]"
    internal_mcp_url: str = "http://localhost:8765/mcp"
    internal_mcp_enabled: bool = True
    # Разрешить MCP-серверы из реестра во внутренних сетях (по умолчанию нет: защита от SSRF)
    mcp_allow_private_urls: bool = False
    # Житель без членства в доме (открыл приложение из лички) подключается к первому (пилотному) дому
    pilot_house_fallback: bool = True

    # Официальные оповещения по регионам (docs/ALERTS.md): воркер опрашивает источники и запускает тревоги
    # в домах нужного региона. В тестах выключено.
    alert_feeds_enabled: bool = True
    alert_feed_interval_seconds: int = 60
    # Тревога из ленты без официального отбоя снимается сама через столько часов
    alert_feed_max_hours: int = 6
    # Сервисный ключ приложения ВКонтакте для wall.get; пусто - источники vk_wall не опрашиваются
    vk_service_token: SecretStr = SecretStr("")

    # Укрытия: заглублённые объекты из OpenStreetMap (зеркала Overpass по очереди) и пешеходный маршрут (OSRM).
    # Зеркала иногда отвечают 504, поэтому таймаут короткий, а результат кэшируется в базе на неделю.
    overpass_urls: list[str] = Field(
        default_factory=lambda: [
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "https://overpass-api.de/api/interpreter",
        ]
    )
    overpass_timeout_seconds: float = 20.0
    # Пешеходный OSRM от FOSSGIS. Демо-сервер router.project-osrm.org знает только машину и молча
    # игнорирует профиль foot: маршрут шёл по дорогам со скоростью ~16 км/ч (проверено 20.10.2026)
    osrm_url: str = "https://routing.openstreetmap.de/routed-foot"
    osrm_timeout_seconds: float = 8.0

    # Подпись временных ссылок на документы. Пусто = выводится из токена бота и ключа MinIO.
    files_secret: SecretStr = SecretStr("")
    files_link_ttl_seconds: int = 15 * 60

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    public_app_url: str = "http://localhost:8080"

    @property
    def bot_token(self) -> str:
        return self.max_bot_token.get_secret_value()

    @property
    def files_signing_key(self) -> bytes:
        raw = self.files_secret.get_secret_value() or f"{self.bot_token}:{self.s3_secret_key.get_secret_value()}"
        return raw.encode()

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
