# 快速开始

本章帮助你快速搭建 KubeAI 开发环境，了解项目结构和基本开发流程。

## 项目概览

KubeAI 是一个 Monorepo 项目，包含以下主要目录：

```
KubeAI/
├── backend/          # FastAPI 后端
├── frontend/         # React 前端
├── infra/            # 基础设施（Helm Chart、Docker 镜像、脚本）
├── docs/             # 项目文档
└── .github/          # CI/CD 工作流
```

## 推荐阅读顺序

1. [环境要求](prerequisites.md) — 了解开发所需的软硬件环境
2. [开发环境搭建](development.md) — 一步步搭建本地开发环境
3. [系统架构总览](../architecture/overview.md) — 了解系统整体设计
