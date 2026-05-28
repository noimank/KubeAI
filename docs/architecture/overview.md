# 系统架构总览

## 架构图

```mermaid
graph TB
    subgraph "用户接入层"
        Browser[浏览器]
        API_CLIENT[API 客户端]
    end

    subgraph "前端应用"
        REACT[React SPA<br/>Ant Design + Tailwind]
        REACT --> API_PROXY[Vite Dev Proxy<br/>/api → :8000]
    end

    subgraph "后端服务 (FastAPI)"
        API[API 网关<br/>/api 前缀]
        API --> MW[中间件栈]
        MW --> AUTH_MW[认证中间件<br/>JWT + Token 黑名单]
        MW --> TENANT_MW[租户中间件<br/>多租户上下文解析]
        MW --> REQ_MW[请求 ID 中间件]

        AUTH_MW --> ENDPOINTS[API 端点<br/>17+ 模块]
        TENANT_MW --> ENDPOINTS
        REQ_MW --> ENDPOINTS

        ENDPOINTS --> SERVICES[服务层<br/>21+ 服务]
        SERVICES --> MODELS[数据模型层<br/>SQLAlchemy 2.0 Async]
    end

    subgraph "数据存储层"
        PG[(PostgreSQL 17)]
        REDIS[(Redis 7)]
        MINIO[(MinIO<br/>对象存储)]
    end

    subgraph "Kubernetes 集群"
        K8S_API[Kubernetes API Server]
        VOLCANO[Volcano 调度器]
        KSERVE[KServe 推理]
        KEDA[KEDA 自动扩缩容]
    end

    subgraph "外部集成"
        HARBOR[Harbor<br/>镜像仓库]
        MLFLOW[MLflow<br/>实验跟踪]
        LABEL_STUDIO[Label Studio<br/>数据标注]
        JUPYTER[JupyterHub<br/>开发环境]
        PROMETHEUS[Prometheus<br/>监控]
    end

    Browser --> REACT
    API_CLIENT --> API
    API_PROXY --> API

    MODELS --> PG
    SERVICES --> REDIS
    SERVICES --> MINIO

    SERVICES --> K8S_API
    K8S_API --> VOLCANO
    K8S_API --> KSERVE
    K8S_API --> KEDA

    SERVICES --> HARBOR
    SERVICES --> MLFLOW
    SERVICES --> LABEL_STUDIO
    SERVICES --> JUPYTER
    SERVICES --> PROMETHEUS
```

## 核心架构分层

KubeAI 后端采用经典的分层架构：

### 1. API 层（端点层）

- 17+ API 端点模块，统一挂载在 `/api` 前缀下
- 负责请求校验（Pydantic Schema）、权限检查（依赖注入）、响应序列化
- 统一使用 `BaseResponse[T]` 包装响应格式：`{success, message, data}`

### 2. 服务层（业务逻辑层）

- 21+ 服务类，封装核心业务逻辑
- 构造器注入 `AsyncSession`（数据库）、`Redis`、`MinIO Client` 等依赖
- 同步外部客户端（MinIO、Harbor）通过 `asyncio.to_thread()` 包装为异步调用

### 3. 集成层（外部系统交互）

- `integrations/k8s/` — Kubernetes 异步客户端（namespace、job、PVC、secret 等）
- `integrations/volcano/` — Volcano VCJob 批处理调度
- `integrations/kserve/` — KServe 推理服务管理
- `integrations/keda/` — KEDA 自动扩缩容
- `integrations/minio/` — MinIO 对象存储
- `integrations/harbor/` — Harbor 镜像仓库
- `integrations/mlflow/` — MLflow 实验跟踪
- `integrations/labelstudio/` — Label Studio 数据标注
- `integrations/jupyterhub/` — JupyterHub 开发环境
- `integrations/prometheus/` — Prometheus 监控指标

### 4. 数据模型层

- SQLAlchemy 2.0 异步 ORM，使用 `Mapped` / `mapped_column` 声明式映射
- 公共 Mixin：`TimestampMixin`（创建/更新时间）、`TenantMixin`（租户 ID）、`SoftDeleteMixin`（软删除）
- 15+ 数据模型，覆盖所有业务实体

## 请求处理流程

一个典型的 API 请求处理流程：

```mermaid
sequenceDiagram
    participant C as 客户端
    participant F as FastAPI
    participant MW as 中间件栈
    participant DI as 依赖注入
    participant EP as API 端点
    participant S as 服务层
    participant DB as PostgreSQL
    participant K8s as Kubernetes

    C->>F: HTTP 请求 /api/...
    F->>MW: RequestIdMiddleware (添加请求 ID)
    MW->>MW: TenantMiddleware (解析租户上下文)
    MW->>DI: get_current_user() (JWT 验证 + Token 黑名单检查)
    DI->>DI: require_permission() (Casbin RBAC 检查)
    DI->>EP: 注入 user, db, tenant 依赖
    EP->>S: 调用服务方法
    S->>DB: 异步数据库操作
    S->>K8s: 异步 Kubernetes API 调用
    S-->>EP: 返回业务结果
    EP-->>C: BaseResponse 包装响应
```

## 技术选型理由

| 技术 | 选型理由 |
|------|----------|
| FastAPI | 原生异步支持、自动 OpenAPI 文档、Pydantic 校验 |
| async SQLAlchemy | 兼容 FastAPI 异步生态，2.0 版本提供类型安全的 ORM |
| Casbin | 灵活的策略引擎，支持 RBAC/ABAC 模型 |
| Volcano | Kubernetes 原生批处理调度器，支持排队、优先级、抢占 |
| KServe | Kubernetes 标准推理协议，支持多框架 |
| KEDA | 基于事件的 Kubernetes 自动扩缩容 |
| Zustand | 轻量级 React 状态管理，API 简洁 |
| TanStack Query | 服务端状态缓存，自动重试和失效 |
| Ant Design | 企业级 React UI 库，组件丰富 |
| MinIO | S3 兼容对象存储，私有化部署 |
