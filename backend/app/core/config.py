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
    TASKIQ_BROKER_DB: int = 1
    TASKIQ_RESULT_BACKEND_DB: int = 2
    TASK_MAX_RETRIES: int = 3
    TASK_RETRY_BACKOFF_SECONDS: int = 10
    INFERENCE_SERVICE_STATUS_SYNC_INTERVAL_SECONDS: int = 60

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 180
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
    MINIO_BUCKET_PREFIX: str = "kubeai-models-"

    DATASET_BASE_PATH: str = "/data/kubeai/datasets"
    ALGORITHM_BASE_PATH: str = "/data/kubeai/algorithms"

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

    # -- Dev environment native pod management
    # Routes are pushed directly to APISIX Admin API at env create/delete time.

    # APISIX Admin API base URL.
    #   Production:     http://kubeai-apisix-admin.kubeai.svc.cluster.local:9180
    #   Docker Desktop: http://localhost:30918 (NodePort)
    KUBEAI_APISIX_ADMIN_URL: str = "http://kubeai-apisix-admin.kubeai.svc.cluster.local:9180"

    # APISIX Admin API key (prod must override with a secure value).
    KUBEAI_APISIX_ADMIN_KEY: str = "edd1c9f034335f136f87ad84b625c8f1"

    # Backend URL reachable from WITHIN the K8s cluster (APISIX forward-auth).
    #   Docker Desktop: http://host.docker.internal:8000 (backend on host)
    #   Production:     http://backend.kubeai.svc.cluster.local:8000
    KUBEAI_BACKEND_INTERNAL_URL: str = "http://backend.kubeai.svc.cluster.local:8000"

    K8S_PLATFORM_NAMESPACE: str = "kubeai"

    KANIKO_IMAGE: str = "gcr.io/kaniko-project/executor:latest"
    MINIO_MC_IMAGE: str = "minio/mc:latest"
    BUSYBOX_IMAGE: str = "busybox:1.36"

    BACKEND_API_URL: str = ""


settings = Settings()
