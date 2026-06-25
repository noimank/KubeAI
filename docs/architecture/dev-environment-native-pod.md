# KubeAI Native Pod 开发环境架构

无需子域名或 DNS 通配符，不依赖外部开发环境调度器。一个域名，路径前缀路由。

## 路由

```
kubeai.example.com/                   → Frontend
kubeai.example.com/api/               → Backend
kubeai.example.com/devenv/<hex>/      → 开发环境 Pod (Jupyter / VS Code / RStudio)
kubeai.example.com/devenv/<hex>/*     → 同上
```

路由通过 **APISIX Admin API** 直接推送——无需 CRD，无需 ingress-controller：

```
Backend → PUT http://kubeai-apisix-admin:9180/apisix/admin/routes/<hex>
  {
    "uri": "/devenv/<hex>/*",
    "host": "kubeai.example.com",
    "priority": 100,
    "plugins": {
      "forward-auth":    → backend /auth-check 验证 JWT (三重冗余传递)
      "proxy-rewrite":   → 仅 VS Code (code-server 无 sub-path 标志)
    },
    "upstream": {
      "nodes": {"devenv-<hex>.<tenant-ns>.svc.cluster.local:8888": 1}
    }
  }
```

``proxy-rewrite`` 仅用于 **VS Code**（code-server 没有 sub-path CLI 标志）。
**Jupyter**（``--ServerApp.base_url``）和 **RStudio**（``--www-root-path``）
自行处理路径前缀，APISIX 不剥离。

## 认证

```
浏览器 → kubeai.example.com/devenv/<hex>/lab
  │ Cookie: kubeai_access_token=JWT (同域名自动携带)
  ▼
APISIX forward-auth → Backend /api/dev-environments/auth-check?env_id=<uuid>&token=<JWT>
  │ 三重冗余 token 传递:
  │   1. URI query param ?token=  (APISIX 解析 $cookie_xxx)
  │   2. Header X-KubeAI-Token    (extra_headers)
  │   3. Cookie 头                (request_headers: [Cookie])
  │ JWT decode → User → DevEnvironment → 权限 → 200/401/403
  │ 200 响应头 X-KubeAI-User 透传到上游
  ▼
Pod:8888 (Jupyter/RStudio: 完整路径; VS Code: proxy-rewrite 剥离前缀)
```

## 数据流

### 创建
```
用户提交 → DB (status=pending)
  → Taskiq worker → DevPodManager.create()
    → K8s: Service (ClusterIP)
    → K8s: Pod
    → APISIX Admin API: PUT route
  → 定时 sync: read Pod status → update DB
```

### 访问
```
点击"打开" → cookie (secure; samesite=strict; path=/)
  → window.open(https://kubeai.example.com/devenv/<hex>/)
```

### 停止/删除
```
停止: delete Pod (保留 Service + route)
删除: delete Pod + Service + APISIX route
```

## 配置

```env
# APISIX Admin API 地址 (backend → APISIX Admin)
KUBEAI_APISIX_ADMIN_URL=http://kubeai-apisix-admin.kubeai.svc.cluster.local:9180

# APISIX Admin API 密钥
KUBEAI_APISIX_ADMIN_KEY=edd1c9f034335f136f87ad84b625c8f1

# APISIX forward-auth 回源 (APISIX Pod → backend Pod)
KUBEAI_BACKEND_INTERNAL_URL=http://backend.kubeai.svc.cluster.local:8000
```

**3 个配置项，全部使用 `svc.cluster.local` 内部 DNS。** 与用户直接访问的 `FRONTEND_URL` 域名完全解耦。

## K8s 内部 DNS

| 调用方 | 目标 | DNS |
|--------|------|-----|
| backend → APISIX Admin | Admin API | `kubeai-apisix-admin.kubeai.svc.cluster.local:9180` |
| APISIX → backend | forward-auth | `backend.kubeai.svc.cluster.local:8000` |
| APISIX → 开发 Pod | upstream proxy | `devenv-<hex>.<tenant-ns>.svc.cluster.local:8888` |

全部是集群内部流量，不经过外部网络。

## 关键文件

| 文件 | 说明 |
|---|---|
| `backend/app/integrations/k8s/dev_pod.py` | Pod/Service 构建 + APISIX Admin API 路由 CRUD |
| `backend/app/api/endpoints/dev_environments.py` | `/auth-check` 端点 (APISIX forward-auth 回调) |
| `backend/app/services/dev_environment_service.py` | 服务层：调用 DevPodManager |
| `backend/app/services/idle_checker.py` | 闲置检测：直接读 Pod status |
| `infra/helm/kubeai/` | APISIX Gateway/etcd 部署 |
