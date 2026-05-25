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
    DEV_ENV_IDLE_TIMEOUT_MINUTES: int = 60
    DEV_ENV_IDLE_CHECK_INTERVAL_SECONDS: int = 300
    RESOURCE_CLEANUP_ENABLED: bool = True
    RESOURCE_CLEANUP_INTERVAL_SECONDS: int = 3600
    RESOURCE_CLEANUP_JOB_MAX_AGE_DAYS: int = 7
    ALLOW_USER_REGISTRATION: bool = True

    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_SCOPES: str = "openid profile email"
    OIDC_DISPLAY_NAME: str = "SSO 登录"
    FRONTEND_URL: str = "http://localhost:3000"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_PREFIX: str = "kubeai-datasets-"

    HARBOR_URL: str = "http://harbor.kubeai.local"
    HARBOR_USERNAME: str = "admin"
    HARBOR_PASSWORD: str = "Harbor12345"
    HARBOR_PROJECT_PREFIX: str = "kubeai-"

    PROMETHEUS_URL: str = "http://localhost:9090"

    API_BASE_URL: str = "http://localhost:8000"

    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_ENABLED: bool = False

    LABEL_STUDIO_URL: str = "http://labelstudio.kubeai.local"
    LABEL_STUDIO_API_TOKEN: str = ""

    JUPYTERHUB_API_URL: str = "http://jupyterhub-hub:8081/hub/api"
    JUPYTERHUB_API_TOKEN: str = ""
    JUPYTERHUB_BASE_URL: str = ""
    JUPYTERHUB_HUB_SERVICE_ACCOUNT: str = ""
    DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS: int = 60

    K8S_PLATFORM_NAMESPACE: str = "kubeai"

    BACKEND_API_URL: str = ""


settings = Settings()
