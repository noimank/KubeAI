from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    APP_NAME: str = "KubeAI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/kubeai"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    IDLE_TIMEOUT_MINUTES: int = 30

    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_SCOPES: str = "openid profile email"
    OIDC_DISPLAY_NAME: str = "SSO 登录"
    FRONTEND_URL: str = "http://localhost:3000"


settings = Settings()
