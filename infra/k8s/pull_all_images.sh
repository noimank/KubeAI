#!/bin/bash
# KubeAI - 拉取所有相关服务镜像
# 用法: bash infra/k8s/pull_all_images.sh

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SUCCESS=0
FAIL=0

pull() {
    local image="$1"
    if docker pull "$image"; then
        echo -e "${GREEN}[OK]${NC} $image"
        ((SUCCESS++))
    else
        echo -e "${RED}[FAIL]${NC} $image"
        ((FAIL++))
    fi
}

echo "=========================================="
echo " KubeAI - 拉取所有服务镜像"
echo "=========================================="
echo ""

# ============================================
# 核心应用镜像
# ============================================
echo -e "${YELLOW}[1/14] 核心应用镜像${NC}"

pull "kubeai-backend:0.1.0"
pull "kubeai-frontend:0.1.0"

# ============================================
# 数据库 & 缓存
# ============================================
echo -e "${YELLOW}[2/14] 数据库 & 缓存${NC}"

pull "postgres:17-alpine"
pull "redis:7-alpine"

# ============================================
# 对象存储
# ============================================
echo -e "${YELLOW}[3/14] 对象存储${NC}"

pull "minio/minio:latest"

# ============================================
# 实验追踪
# ============================================
echo -e "${YELLOW}[4/14] MLflow${NC}"

pull "ghcr.io/mlflow/mlflow:v3.12.0"

# ============================================
# 数据标注
# ============================================
echo -e "${YELLOW}[5/14] Label Studio${NC}"

pull "heartexlabs/label-studio:1.23.0"

# ============================================
# JupyterHub
# ============================================
echo -e "${YELLOW}[6/14] JupyterHub${NC}"

pull "quay.io/jupyterhub/k8s-hub:4.3.5"
pull "quay.io/jupyterhub/configurable-http-proxy:5.2.0"
pull "quay.io/jupyterhub/k8s-network-tools:4.3.5"
pull "quay.io/jupyterhub/k8s-image-awaiter:4.3.5"
pull "jupyter/datascience-notebook:latest"
pull "registry.k8s.io/pause:3.10.1"
pull "registry.k8s.io/kube-scheduler:v1.30.14"

# ============================================
# Harbor 容器仓库
# ============================================
echo -e "${YELLOW}[7/14] Harbor${NC}"

pull "docker.io/goharbor/harbor-core:v2.15.1"
pull "docker.io/goharbor/harbor-jobservice:v2.15.1"
pull "docker.io/goharbor/harbor-portal:v2.15.1"
pull "docker.io/goharbor/registry-photon:v2.15.1"
pull "docker.io/goharbor/harbor-registryctl:v2.15.1"
pull "docker.io/goharbor/harbor-db:v2.15.1"
pull "docker.io/goharbor/redis-photon:v2.15.1"
pull "docker.io/goharbor/trivy-adapter-photon:v2.15.1"

# ============================================
# KServe 推理服务
# ============================================
echo -e "${YELLOW}[8/14] KServe${NC}"

pull "kserve/kserve-controller:v0.17.0"
pull "quay.io/brancz/kube-rbac-proxy:v0.18.0"
pull "kserve/storage-initializer:v0.17.0"
pull "kserve/agent:v0.17.0"
pull "kserve/router:v0.17.0"
pull "kserve/art-explainer:v0.17.0"

# ============================================
# KEDA 自动扩缩容
# ============================================
echo -e "${YELLOW}[9/14] KEDA${NC}"

pull "ghcr.io/kedacore/keda:2.19.0"
pull "ghcr.io/kedacore/keda-metrics-apiserver:2.19.0"
pull "ghcr.io/kedacore/keda-admission-webhooks:2.19.0"

# ============================================
# Volcano 批调度器
# ============================================
echo -e "${YELLOW}[10/14] Volcano${NC}"

pull "docker.io/volcanosh/vc-webhook-manager:v1.14.2"
pull "docker.io/volcanosh/vc-controller-manager:v1.14.2"
pull "docker.io/volcanosh/vc-scheduler:v1.14.2"

# ============================================
# Prometheus 监控栈
# ============================================
echo -e "${YELLOW}[11/14] Prometheus 监控栈${NC}"

pull "quay.io/prometheus/prometheus:v3.1.0"
pull "docker.io/grafana/grafana:11.4.0"
pull "quay.io/prometheus-operator/prometheus-operator:v0.79.2"
pull "registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.14.0"
pull "quay.io/kiwigrid/k8s-sidecar:1.28.0"
pull "docker.io/bats/bats:v1.4.1"
pull "registry.k8s.io/ingress-nginx/kube-webhook-certgen:v20221220-controller-v1.5.1-58-g787ea74b6"

# ============================================
# GPU 监控
# ============================================
echo -e "${YELLOW}[12/14] DCGM Exporter (GPU)${NC}"

pull "nvcr.io/nvidia/k8s/dcgm-exporter:3.3.9-3.6.1-ubuntu22.04"

# ============================================
# 镜像构建工具 (后端 K8s Job 使用)
# ============================================
echo -e "${YELLOW}[13/14] 镜像构建 & 工具镜像${NC}"

pull "gcr.io/kaniko-project/executor:latest"
pull "minio/mc:latest"
pull "busybox:1.36"

# ============================================
# 构建基础镜像 (Dockerfile 中使用)
# ============================================
echo -e "${YELLOW}[14/14] 构建基础镜像${NC}"

pull "python:3.12-slim"
pull "ghcr.io/astral-sh/uv:latest"
pull "node:20-alpine"
pull "nginx:alpine"

# ============================================
# 开发环境镜像 (可选)
# ============================================
echo -e "${YELLOW}[可选] 开发环境镜像${NC}"

pull "codercom/code-server:latest"
pull "nvidia/cuda:12.4.1-devel-ubuntu22.04"
pull "quay.io/jupyter/scipy-notebook:latest"
pull "quay.io/jupyter/pytorch-notebook:cuda12-latest"
pull "quay.io/jupyter/tensorflow-notebook:cuda-latest"
pull "rocker/verse:4.4.3"
pull "rocker/ml:4.4.3-cuda12.4"

# ============================================
# 汇总
# ============================================
echo ""
echo "=========================================="
echo -e " 完成: ${GREEN}${SUCCESS} 成功${NC}, ${RED}${FAIL} 失败${NC}"
echo "=========================================="

if ((FAIL > 0)); then
    exit 1
fi
