# 环境要求

## 必要软件

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.12 | 后端开发语言 |
| Node.js | >= 20 | 前端运行时 |
| pnpm | >= 9 | 前端包管理器 |
| uv | >= 0.5 | Python 包管理器（替代 pip） |
| Docker | >= 24 | 容器运行时和镜像构建 |
| Kubernetes | >= 1.28 | 容器编排平台 |
| Helm | >= 3.14 | Kubernetes 包管理器 |
| Git | >= 2.40 | 版本控制 |

## 推荐开发工具

| 工具 | 用途 |
|------|------|
| VS Code / JetBrains | 代码编辑器 |
| kubectl | Kubernetes 命令行工具 |
| k9s | Kubernetes 终端 UI |
| DBeaver / pgAdmin | PostgreSQL 数据库管理 |
| RedisInsight | Redis 管理工具 |
| Postman / httpie | API 测试工具 |

## 外部服务

开发环境通过 Helm Chart 部署以下服务（`values-dev.yaml`）：

| 服务 | 用途 | 开发环境端口 |
|------|------|-------------|
| PostgreSQL 17 | 主数据库 | NodePort 30432 |
| Redis 7 | 缓存/会话/消息 | NodePort 30379 |
| MinIO | 对象存储 | API: 30900, Console: 30901 |
| MLflow | 实验跟踪 | NodePort 30500 |
| Label Studio | 数据标注 | NodePort 30800 |
| KServe | 模型推理 | 集群内访问 |
| JupyterHub | 开发环境 | NodePort 30801 |

## 硬件建议

| 配置项 | 最低要求 | 推荐配置 |
|--------|----------|----------|
| CPU | 4 核 | 8 核+ |
| 内存 | 8 GB | 16 GB+ |
| 磁盘 | 40 GB | 100 GB+ |
| GPU（可选） | NVIDIA GPU | 用于模型训练和推理 |

!!! tip "提示"
    如果不需要 GPU 训练和推理功能，可以在无 GPU 的环境中开发。前端和大部分后端功能不依赖 GPU。
