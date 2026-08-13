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
    TRAINING_JOB_STATUS_SYNC_INTERVAL_SECONDS: int = 60

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 180
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- 身份解析层 (IdentityResolver) 缓存 TTL (秒)
    # identity:<user_id>:<user_token_version>  — 解析后的身份, user/tenant 禁用时主动失效
    IDENTITY_CACHE_TTL_SECONDS: int = 300
    # tenant_status:<tenant_id> — 租户启用状态, 禁用时主动覆盖, 此 TTL 仅兜底
    TENANT_STATUS_CACHE_TTL_SECONDS: int = 120

    IDLE_TIMEOUT_MINUTES: int = 30
    DEV_ENV_IDLE_TIMEOUT_MINUTES: int = 60
    DEV_ENV_IDLE_CHECK_INTERVAL_SECONDS: int = 300
    RESOURCE_CLEANUP_ENABLED: bool = True
    RESOURCE_CLEANUP_INTERVAL_SECONDS: int = 3600
    RESOURCE_CLEANUP_JOB_MAX_AGE_DAYS: int = 7
    ALLOW_USER_REGISTRATION: bool = True
    ENABLE_BUSINESS_ALGORITHM: bool = False

    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_SCOPES: str = "openid profile email"
    OIDC_DISPLAY_NAME: str = "SSO 登录"
    OIDC_AUTO_REDIRECT: bool = False
    FRONTEND_URL: str = "http://localhost:3000"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_PREFIX: str = "kubeai-models-"
    # 集群内 Pod (如 model-pull initContainer) 访问 MinIO 的地址, 带 scheme.
    #   standalone 拓扑: http://minio.kubeai.svc.cluster.local:9000
    #   Helm 拓扑:       http://kubeai-minio.kubeai.svc.cluster.local:9000
    # 与 MINIO_ENDPOINT (backend 进程主机侧地址) 区分.
    MINIO_INTERNAL_ENDPOINT: str = "http://minio.kubeai.svc.cluster.local:9000"

    DATASET_BASE_PATH: str = "/data/kubeai/datasets"
    ALGORITHM_BASE_PATH: str = "/data/kubeai/algorithms"
    MODEL_BASE_PATH: str = "/data/kubeai/models"

    HARBOR_URL: str = "http://harbor.kubeai.local"
    HARBOR_USERNAME: str = "admin"
    HARBOR_PASSWORD: str = "Harbor12345"
    HARBOR_PROJECT_PREFIX: str = "kubeai-"

    PROMETHEUS_URL: str = "http://localhost:9090"

    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    LABEL_STUDIO_URL: str = "http://labelstudio.kubeai.local"
    LABEL_STUDIO_API_TOKEN: str = ""

    # -- 业务算法库 (balibrary) 独立服务地址
    BALIBRARY_URL: str = "http://balibrary.kubeai.svc:8800"

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

    # TensorBoard sidecar 镜像与端口. 镜像地址在本地/生产/不同 registry 间需可覆盖.
    TENSORBOARD_IMAGE: str = "kubeai-tensorboard:latest"
    TENSORBOARD_PORT: int = 6006

    # -- 数据探索
    DATA_EXPLORE_MAX_ROWS: int = 1000
    DATA_EXPLORE_QUERY_TIMEOUT: int = 30

    # -- 自动超参调优 (Optuna)
    # 兜底驱动周期 (秒): 主路径为 trial job 终态事件触发的 finalize_trial_task, 此处仅作 safety-net
    # (覆盖 watcher 漏事件 / 补发新 trial). interval_to_cron 最细到分钟.
    TUNING_DRIVE_INTERVAL_SECONDS: int = 180
    # trial job 成功但 MLflow 指标暂不可读时, 在此秒数内反复重试 (读不到就留到下个 tick),
    # 超时仍未上报则判 FAIL, 避免 MLflow 延迟导致 trial 误判永久失败.
    TUNING_METRIC_GRACE_SECONDS: int = 600
    # Optuna RDBStorage 同步 URL. 必须指向独立数据库 (与 DATABASE_URL 不同库), 不得留空:
    # Optuna 与平台各自走 Alembic, 共库会共用 alembic_version 导致建表/迁移冲突.
    OPTUNA_DATABASE_URL: str = ""
    OPTUNA_STORAGE_HEARTBEAT_SECONDS: int = 60
    # Optuna RDBStorage 连接池 (同步 psycopg2 引擎, 与平台 asyncpg 池相互独立).
    # RDBStorage 默认 pool_size=5 且无 pool_pre_ping; 偶发 StorageInternalError 多源于
    # 死锁/锁等待超时与陈旧连接, 这里显式配置连接池并探测陈旧连接. 池尺寸按调优并发取小值.
    OPTUNA_DB_POOL_SIZE: int = 5
    OPTUNA_DB_MAX_OVERFLOW: int = 5
    OPTUNA_DB_POOL_RECYCLE_SECONDS: int = 3600
    OPTUNA_DB_POOL_TIMEOUT_SECONDS: int = 10


settings = Settings()
