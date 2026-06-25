# 后端架构

## 目录结构

```
backend/
├── app/
│   ├── main.py                  # FastAPI 入口，中间件和路由注册
│   ├── api/
│   │   ├── deps.py              # 依赖注入（认证、权限、数据库会话）
│   │   └── endpoints/           # 17+ API 端点模块
│   │       ├── router.py        # 路由注册中心
│   │       ├── auth.py          # 认证（登录、注册、Token 刷新）
│   │       ├── users.py         # 用户管理
│   │       ├── tenants.py       # 租户管理
│   │       ├── datasets.py      # 数据集管理
│   │       ├── training_jobs.py # 训练任务
│   │       ├── inference_services.py  # 推理服务
│   │       └── ...
│   ├── core/
│   │   ├── config.py            # Pydantic Settings 配置
│   │   ├── security.py          # 密码哈希、JWT 创建
│   │   ├── token_blacklist.py   # Redis Token 黑名单
│   │   ├── casbin.py            # Casbin RBAC 引擎
│   │   ├── permissions.py       # 权限策略定义
│   │   ├── database.py          # SQLAlchemy 引擎和会话
│   │   ├── redis.py             # Redis 连接池
│   │   ├── exceptions.py        # 异常层次结构
│   │   ├── events.py            # 启动/关闭事件
│   │   ├── ws_manager.py        # WebSocket 连接管理
│   │   └── ws_pubsub.py         # WebSocket 发布/订阅
│   ├── models/                  # 15+ SQLAlchemy 数据模型
│   ├── schemas/                 # Pydantic 请求/响应 Schema
│   ├── services/                # 21+ 业务服务
│   ├── integrations/            # 外部系统集成客户端
│   ├── middleware/              # 中间件（错误处理、请求 ID、租户）
│   └── utils/                   # 工具函数
├── alembic/                     # 数据库迁移（38+ 迁移文件）
├── tests/                       # 测试套件
│   ├── unit/                    # 单元测试（40+ 文件）
│   └── integration/             # 集成测试（13+ 文件）
├── pyproject.toml               # 项目配置和依赖
├── ruff.toml                    # Ruff Lint 配置
└── .env.example                 # 环境变量模板
```

## 应用入口

`app/main.py` 是应用入口，负责：

1. 创建 FastAPI 实例
2. 注册中间件（按顺序）：
   - `RequestIdMiddleware` — 为每个请求添加唯一 ID
   - `TenantMiddleware` — 解析多租户上下文
3. 注册异常处理器（`AppException` + 全局异常兜底）
4. 挂载路由：
   - `api_router`（REST API，`/api` 前缀）
   - `ws_router`（WebSocket，`/api` 前缀）

## 核心模块

### 配置管理（`core/config.py`）

使用 `pydantic_settings.BaseSettings` 管理所有配置，自动从 `.env` 文件读取：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # 基础配置
    APP_NAME: str = "KubeAI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # 数据库
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20

    # 认证
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 180
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ... 更多配置
```

### 认证与安全（`core/security.py`）

| 功能 | 实现方式 |
|------|----------|
| 密码哈希 | bcrypt（通过 `asyncio.to_thread` 异步执行） |
| Access Token | JWT HS256，默认 30 分钟过期 |
| Refresh Token | JWT HS256，默认 7 天过期 |
| API Token | `sk-<hex>` 前缀格式，SHA-256 哈希存储 |
| Token 吊销 | Redis 黑名单（基于 JTI claim） |
| 账户锁定 | 5 次失败后锁定 15 分钟（Redis TTL） |

### 依赖注入（`api/deps.py`）

FastAPI 依赖注入提供横切关注点：

| 依赖 | 功能 |
|------|------|
| `get_db()` | 异步数据库会话（自动提交/回滚） |
| `get_current_user()` | JWT 验证 + 黑名单检查 + 用户加载 |
| `require_permission(resource, action)` | Casbin RBAC 权限检查 |
| `require_tenant_access(tenant_id)` | 租户隔离检查（管理员跳过） |

### 异常处理（`core/exceptions.py`）

自定义异常层次结构，所有异常消息默认中文：

| 异常类 | HTTP 状态码 | 默认消息 |
|--------|-------------|----------|
| `AppException` | 500 | 服务内部错误 |
| `NotFoundException` | 404 | 资源不存在 |
| `BadRequestException` | 400 | 请求参数错误 |
| `UnauthorizedException` | 401 | 未授权访问 |
| `ForbiddenException` | 403 | 权限不足 |
| `ConflictException` | 409 | 资源冲突 |
| `QuotaExceededException` | 422 | 配额已超出 |
| `ExternalServiceException` | 502 | 外部服务异常 |

## 服务层

所有服务通过构造器注入 `AsyncSession`：

```python
class DatasetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_dataset(self, data: DatasetCreate, tenant_id: str) -> Dataset:
        ...
```

核心服务概览：

| 服务 | 职责 |
|------|------|
| `AuthService` | 注册/登录/锁定/刷新/登出 |
| `TenantService` | K8s 命名空间 + ResourceQuota + NetworkPolicy，失败回滚 |
| `DatasetService` | MinIO 数据集/版本管理 + 预签名 URL |
| `TrainingJobService` | Volcano VCJob 创建，PVC 数据集挂载，配额追踪 |
| `InferenceService` | KServe 推理服务 + KEDA 自动扩缩容 + 金丝雀发布 |
| `AnnotationService` | Label Studio 标注项目 + XML 模板 + 标注写回 |
| `DevEnvironmentService` | 原生 K8s Pod 环境 + 数据集挂载 + 空闲自动停止 |
| `ImageService` | K8s Job 自定义镜像构建 + Harbor 推送 |
| `ExperimentService` | MLflow 实验跟踪 + 实验复现为训练任务 |
| `MonitoringService` | Prometheus 指标采集 + WebSocket 推送 |
| `IdleChecker` | 后台空闲环境检测和自动停止 |
| `ResourceCleaner` | 后台过期资源清理 |

## 集成层

所有 Kubernetes 操作使用 `kubernetes_asyncio` 异步客户端：

```python
# 异步 K8s 客户端示例
async with client.ApiClient() as api:
    v1 = client.CoreV1Api(api)
    namespace = await v1.read_namespace(name="kubeai-tenant-1")
```

同步客户端（MinIO、Harbor）通过 `asyncio.to_thread()` 包装：

```python
# 同步客户端异步包装
result = await asyncio.to_thread(self.minio_client.list_objects, bucket_name)
```

## 启动流程

应用启动时自动执行以下操作：

1. 初始化 Redis 连接池
2. 初始化 Casbin RBAC 引擎并加载权限策略
3. 创建默认租户和管理员用户（如不存在）
4. 为默认租户创建 Kubernetes 命名空间
5. 初始化集成客户端（MinIO、Harbor、Prometheus、Label Studio、MLflow）
6. 启动 `IdleChecker` 后台任务
7. 启动 `ResourceCleaner` 后台任务
8. 启动指标推送循环（每 30 秒通过 WebSocket 推送集群指标）
