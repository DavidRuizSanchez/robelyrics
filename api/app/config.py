from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,  # las vars vienen del entorno docker, no de un .env dentro del contenedor
        case_sensitive=False,
        extra="ignore",
    )

    # DB
    database_url: str = Field(..., alias="DATABASE_URL")

    # Vector DB
    qdrant_url: str = Field("http://qdrant:6333", alias="QDRANT_URL")

    # Auth
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_algo: str = Field("HS256", alias="JWT_ALGO")
    jwt_ttl_min: int = Field(43_200, alias="JWT_TTL_MIN")
    bcrypt_rounds: int = Field(12, alias="BCRYPT_ROUNDS")
    admin_email: str | None = Field(None, alias="ADMIN_EMAIL")
    admin_password: str | None = Field(None, alias="ADMIN_PASSWORD")

    # External services
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    genius_token: str | None = Field(None, alias="GENIUS_TOKEN")
    reddit_client_id: str | None = Field(None, alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = Field(None, alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str | None = Field(None, alias="REDDIT_USER_AGENT")
    youtube_api_key: str | None = Field(None, alias="YOUTUBE_API_KEY")

    # Email — dos backends posibles, se elige por config:
    #   1) SMTP genérico (Gmail con app-password recomendado para uso personal)
    #   2) Resend (preferible cuando haya dominio verificado en producción)
    smtp_host: str | None = Field(None, alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str | None = Field(None, alias="SMTP_USER")
    smtp_password: str | None = Field(None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(None, alias="SMTP_FROM")
    smtp_from_name: str = Field("Entre Interiores", alias="SMTP_FROM_NAME")

    resend_api_key: str | None = Field(None, alias="RESEND_API_KEY")
    resend_from_email: str = Field("hola@entreinteriores.com", alias="RESEND_FROM_EMAIL")

    site_url: str = Field("http://localhost:3001", alias="SITE_URL")

    # Términos: versión vigente. Al cambiar, los users tienen que re-aceptar.
    terms_version: str = Field("2026-05-02", alias="TERMS_VERSION")

    # Logging
    api_log_level: str = Field("info", alias="API_LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
