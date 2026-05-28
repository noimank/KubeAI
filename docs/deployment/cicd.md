# CI/CD 流水线

KubeAI 使用 GitHub Actions 实现 CI/CD，包含三个工作流。

## CI 工作流（ci.yml）

**触发条件：** PR 和 Push 到 `main` / `dev` 分支

### 任务矩阵

```mermaid
graph TD
    PR[PR / Push] --> BL[Backend Lint]
    PR --> BT[Backend Test]
    PR --> FL[Frontend Lint]
    PR --> FT[Frontend Test]
    PR --> HL[Helm Lint]

    BL --> |ruff check| R1[代码检查]
    BL --> |ruff format --check| R2[格式检查]
    BL --> |mypy app/| R3[类型检查]

    BT --> |PostgreSQL 17| S1[服务容器]
    BT --> |Redis 7| S2[服务容器]
    BT --> |pytest tests/unit/| S3[单元测试]

    FL --> |pnpm lint| F1[ESLint]
    FL --> |pnpm typecheck| F2[TypeScript]

    FT --> |pnpm test| F3[Vitest]

    HL --> |helm lint| H1[Chart 检查]
```

所有任务并行执行，任一任务失败将阻止 PR 合并。

## 构建工作流（build.yml）

**触发条件：** Push 到 `main` / `dev` 分支，版本 Tag（`v*`）

### 构建流程

| 步骤 | 说明 |
|------|------|
| Checkout | 检出代码 |
| Docker Build | 多阶段构建 Docker 镜像 |
| Registry Login | 登录 GitHub Container Registry (ghcr.io) |
| Push | 推送镜像（commit SHA 标签 + latest） |

### 镜像命名

```
ghcr.io/<org>/backend:<sha>    # 后端镜像
ghcr.io/<org>/frontend:<sha>   # 前端镜像
```

镜像仅在 push 事件时推送（PR 仅构建不推送）。

## 发布工作流（release.yml）

**触发条件：** 版本 Tag（`v*`，如 `v0.1.0`）

### 发布流程

```mermaid
sequenceDiagram
    participant D as 开发者
    participant G as GitHub
    participant R as Registry
    participant H as Helm

    D->>G: git tag v0.1.0 && git push --tags
    G->>G: 构建 backend + frontend 镜像
    G->>R: 推送镜像 (v0.1.0 + latest)
    G->>H: 打包 Helm Chart (version: 0.1.0)
    G->>G: 创建 GitHub Release
    G-->>D: Release 包含 Chart .tgz 附件
```

## 本地开发验证

在提交 PR 之前，建议本地运行检查：

```bash
# 后端
cd backend/
uv run ruff check .
uv run ruff format --check .
uv run mypy app/
uv run pytest tests/unit/

# 前端
cd frontend/
pnpm lint
pnpm typecheck
pnpm test

# Helm
helm lint infra/helm/kubeai/
```
