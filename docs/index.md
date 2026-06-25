# KubeAI 文档

KubeAI 是一个基于 Kubernetes 的云原生 AI/ML 平台，提供从数据管理、模型训练、模型部署到数据标注的全生命周期管理能力。

## 平台特性

- **多云原生**：基于 Kubernetes 构建，支持多租户隔离，自动资源调度
- **全生命周期**：涵盖数据集管理、模型训练、实验跟踪、模型注册、推理服务部署
- **智能调度**：集成 Volcano 批处理调度器，支持 GPU 资源管理和优先级调度
- **弹性伸缩**：基于 KEDA 的推理服务自动扩缩容，支持金丝雀发布
- **数据标注**：集成 Label Studio，支持图像分类、目标检测、语义分割等多种标注类型
- **开发环境**：基于原生 K8s Pod 的交互式开发环境，支持数据集挂载和空闲自动停止
- **镜像管理**：自定义镜像构建，推送到 Harbor 镜像仓库
- **权限管理**：四层角色体系（管理员/MLOps/工程师/标注员），Casbin RBAC 权限控制
- **监控告警**：Prometheus + Grafana 集群监控，GPU 指标采集，资源配额管理

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | Python 3.12 + FastAPI + async SQLAlchemy 2.0 |
| 前端框架 | React 18 + TypeScript + Ant Design 5 + Tailwind CSS |
| 数据库 | PostgreSQL 17 |
| 缓存 | Redis 7 |
| 对象存储 | MinIO（S3 兼容） |
| 容器镜像仓库 | Harbor |
| 任务调度 | Kubernetes + Volcano 批处理调度器 |
| 模型推理 | KServe + KEDA 自动扩缩容 |
| 实验跟踪 | MLflow |
| 数据标注 | Label Studio |
| 开发环境 | 原生 K8s Pod + APISIX 路由 |
| 监控 | Prometheus + DCGM Exporter |
| 部署 | 本地依赖 Helm Chart + 生产 Kubernetes Manifests |

## 快速导航

- [:rocket: 快速开始](getting-started/index.md) — 了解环境要求和开发环境搭建
- [:building_construction: 架构设计](architecture/index.md) — 深入了解系统架构和设计理念
- [:gear: 功能模块](features/index.md) — 了解各功能模块的使用方法
- [:book: API 参考](api/index.md) — 完整的 REST API 接口文档
- [:rocket: 部署运维](deployment/index.md) — 生产环境部署和运维指南
- [:wrench: 开发指南](development-guide/index.md) — 编码规范和开发最佳实践
