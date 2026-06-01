#!/bin/bash
# KubeAI - 拉取所有相关服务镜像，并推送到私有仓库
# 用法: bash infra/k8s/pull_all_images.sh
#
# 可选环境变量:
#   PRIVATE_REGISTRY_PREFIX=hub.uimpcloud.com/kubeai
#   PULL_RETRIES=3

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PRIVATE_REGISTRY_PREFIX="${PRIVATE_REGISTRY_PREFIX:-hub.uimpcloud.com/kubeai}"
PULL_RETRIES="${PULL_RETRIES:-3}"

declare -a REQUIRED=()
declare -a OPTIONAL=()
declare -a LOCAL=()

PULL_OK=0
PULL_SKIP=0
PULL_FAIL=0
TAG_OK=0
TAG_FAIL=0
PUSH_OK=0
PUSH_FAIL=0

section() {
    echo -e "${YELLOW}$1${NC}"
}

target_image() {
    local image="$1"
    echo "${PRIVATE_REGISTRY_PREFIX}/${image##*/}"
}

pull_with_retry() {
    local image="$1"
    local attempt

    for ((attempt = 1; attempt <= PULL_RETRIES; attempt += 1)); do
        if docker pull "$image"; then
            return 0
        fi
        echo -e "${YELLOW}[RETRY ${attempt}/${PULL_RETRIES}]${NC} $image"
    done

    docker image inspect "$image" >/dev/null 2>&1
}

tag_image() {
    local source="$1"
    local target
    target="$(target_image "$source")"

    if docker tag "$source" "$target"; then
        echo -e "${GREEN}[TAG OK]${NC} $source -> $target"
        ((TAG_OK += 1))
    else
        echo -e "${RED}[TAG FAIL]${NC} $source -> $target"
        ((TAG_FAIL += 1))
    fi
}

push_image() {
    local source="$1"
    local target
    target="$(target_image "$source")"

    if docker push "$target"; then
        echo -e "${GREEN}[PUSH OK]${NC} $target"
        ((PUSH_OK += 1))
    else
        echo -e "${RED}[PUSH FAIL]${NC} $target"
        ((PUSH_FAIL += 1))
    fi
}

echo "=========================================="
echo " KubeAI - 拉取、Tag 并推送所有服务镜像"
echo " 目标仓库前缀: ${PRIVATE_REGISTRY_PREFIX}"
echo "=========================================="
echo ""

# ============================================
# 本地构建镜像 (需先 docker build)
# ============================================
section "[本地] 核心应用镜像 (需先构建)"

LOCAL+=("kubeai-backend:0.1.0")
LOCAL+=("kubeai-frontend:0.1.0")

# ============================================
# 数据库 & 缓存
# ============================================
section "[1/13] 数据库 & 缓存"

REQUIRED+=("postgres:17-alpine")
REQUIRED+=("redis:7-alpine")

# ============================================
# 对象存储
# ============================================
section "[2/13] 对象存储"

REQUIRED+=("minio/minio:latest")

# ============================================
# 实验追踪
# ============================================
section "[3/13] MLflow"

REQUIRED+=("ghcr.io/mlflow/mlflow:v3.12.0")

# ============================================
# 数据标注
# ============================================
section "[4/13] Label Studio"

REQUIRED+=("heartexlabs/label-studio:1.23.0")

# ============================================
# JupyterHub
# ============================================
section "[5/13] JupyterHub"

REQUIRED+=("quay.io/jupyterhub/k8s-hub:4.3.5")
REQUIRED+=("quay.io/jupyterhub/configurable-http-proxy:5.2.0")
REQUIRED+=("quay.io/jupyterhub/k8s-network-tools:4.3.5")
REQUIRED+=("quay.io/jupyterhub/k8s-image-awaiter:4.3.5")
REQUIRED+=("jupyter/datascience-notebook:latest")
REQUIRED+=("registry.k8s.io/pause:3.10.1")
REQUIRED+=("registry.k8s.io/kube-scheduler:v1.30.14")

# ============================================
# Harbor 容器仓库
# ============================================
section "[6/13] Harbor"

REQUIRED+=("docker.io/goharbor/harbor-core:v2.15.1")
REQUIRED+=("docker.io/goharbor/harbor-jobservice:v2.15.1")
REQUIRED+=("docker.io/goharbor/harbor-portal:v2.15.1")
REQUIRED+=("docker.io/goharbor/registry-photon:v2.15.1")
REQUIRED+=("docker.io/goharbor/harbor-registryctl:v2.15.1")
REQUIRED+=("docker.io/goharbor/harbor-db:v2.15.1")
REQUIRED+=("docker.io/goharbor/redis-photon:v2.15.1")
REQUIRED+=("docker.io/goharbor/trivy-adapter-photon:v2.15.1")

# ============================================
# KServe 推理服务
# ============================================
section "[7/13] KServe"

REQUIRED+=("kserve/kserve-controller:v0.17.0")
REQUIRED+=("quay.io/brancz/kube-rbac-proxy:v0.18.0")
REQUIRED+=("kserve/storage-initializer:v0.17.0")
REQUIRED+=("kserve/agent:v0.17.0")
REQUIRED+=("kserve/router:v0.17.0")
REQUIRED+=("kserve/art-explainer:v0.17.0")

# ============================================
# KEDA 自动扩缩容
# ============================================
section "[8/13] KEDA"

REQUIRED+=("ghcr.io/kedacore/keda:2.19.0")
REQUIRED+=("ghcr.io/kedacore/keda-metrics-apiserver:2.19.0")
REQUIRED+=("ghcr.io/kedacore/keda-admission-webhooks:2.19.0")

# ============================================
# Volcano 批调度器
# ============================================
section "[9/13] Volcano"

REQUIRED+=("docker.io/volcanosh/vc-webhook-manager:v1.14.2")
REQUIRED+=("docker.io/volcanosh/vc-controller-manager:v1.14.2")
REQUIRED+=("docker.io/volcanosh/vc-scheduler:v1.14.2")

# ============================================
# Prometheus 监控栈
# ============================================
section "[10/13] Prometheus 监控栈"

REQUIRED+=("quay.io/prometheus/prometheus:v3.1.0")
REQUIRED+=("docker.io/grafana/grafana:11.4.0")
REQUIRED+=("quay.io/prometheus-operator/prometheus-operator:v0.79.2")
REQUIRED+=("registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.14.0")
REQUIRED+=("quay.io/kiwigrid/k8s-sidecar:1.28.0")
REQUIRED+=("docker.io/bats/bats:v1.4.1")
REQUIRED+=("registry.k8s.io/ingress-nginx/kube-webhook-certgen:v20221220-controller-v1.5.1-58-g787ea74b6")

# ============================================
# GPU 监控
# ============================================
section "[11/13] DCGM Exporter (GPU)"

REQUIRED+=("nvcr.io/nvidia/k8s/dcgm-exporter:3.3.9-3.6.1-ubuntu22.04")

# ============================================
# 镜像构建工具 (后端 K8s Job 使用)
# ============================================
section "[12/13] 镜像构建 & 工具镜像"

REQUIRED+=("gcr.io/kaniko-project/executor:latest")
REQUIRED+=("minio/mc:latest")
REQUIRED+=("busybox:1.36")

# ============================================
# 构建基础镜像 (Dockerfile 中使用)
# ============================================
section "[13/13] 构建基础镜像"

REQUIRED+=("python:3.12-slim")
REQUIRED+=("ghcr.io/astral-sh/uv:latest")
REQUIRED+=("node:24-alpine")
REQUIRED+=("nginx:alpine")

# ============================================
# 开发环境镜像 (可选 - 失败不阻塞)
# ============================================
section "[可选] 开发环境镜像"

OPTIONAL+=("codercom/code-server:latest")
OPTIONAL+=("nvidia/cuda:12.4.1-devel-ubuntu22.04")
OPTIONAL+=("quay.io/jupyter/scipy-notebook:latest")
OPTIONAL+=("quay.io/jupyter/pytorch-notebook:cuda12-latest")
OPTIONAL+=("quay.io/jupyter/tensorflow-notebook:cuda-latest")
OPTIONAL+=("rocker/verse:4.4.3")
OPTIONAL+=("rocker/ml:4.4")

# ============================================
# 阶段 1: 检查本地构建镜像
# ============================================
echo ""
echo "=========================================="
echo " 阶段 1/4: 检查本地构建镜像 (${#LOCAL[@]} 个)"
echo "=========================================="

for image in "${LOCAL[@]}"; do
    if docker image inspect "$image" >/dev/null 2>&1; then
        echo -e "${GREEN}[LOCAL OK]${NC} $image"
    else
        echo -e "${RED}[MISSING]${NC} $image"
        echo -e "  请先构建:"
        echo -e "    docker build -t kubeai-backend:0.1.0 -f infra/images/backend/Dockerfile ."
        echo -e "    docker build -t kubeai-frontend:0.1.0 -f infra/images/frontend/Dockerfile ."
        exit 1
    fi
done

# ============================================
# 阶段 2: 拉取远程镜像
# ============================================
echo ""
echo "=========================================="
echo " 阶段 2/4: 拉取远程镜像 (必需 ${#REQUIRED[@]} + 可选 ${#OPTIONAL[@]})"
echo "=========================================="

for image in "${REQUIRED[@]}"; do
    if pull_with_retry "$image"; then
        echo -e "${GREEN}[PULL OK]${NC} $image"
        ((PULL_OK += 1))
    else
        echo -e "${RED}[PULL FAIL]${NC} $image"
        ((PULL_FAIL += 1))
    fi
done

if ((PULL_FAIL > 0)); then
    echo ""
    echo "=========================================="
    echo -e " 必需镜像拉取失败: ${RED}${PULL_FAIL} 个${NC}，已停止。"
    echo "=========================================="
    exit 1
fi

declare -a OPTIONAL_AVAILABLE=()

for image in "${OPTIONAL[@]}"; do
    if pull_with_retry "$image"; then
        echo -e "${GREEN}[PULL OK]${NC} $image"
        ((PULL_OK += 1))
        OPTIONAL_AVAILABLE+=("$image")
    else
        echo -e "${YELLOW}[SKIP]${NC} $image (可选镜像，跳过)"
        ((PULL_SKIP += 1))
    fi
done

# ============================================
# 阶段 3: 重新 Tag 到私有仓库
# ============================================
ALL_IMAGES=("${LOCAL[@]}" "${REQUIRED[@]}" "${OPTIONAL_AVAILABLE[@]}")

echo ""
echo "=========================================="
echo " 阶段 3/4: Tag 镜像到私有仓库 (${#ALL_IMAGES[@]} 个)"
echo "=========================================="

for image in "${ALL_IMAGES[@]}"; do
    tag_image "$image"
done

if ((TAG_FAIL > 0)); then
    echo ""
    echo "=========================================="
    echo -e " Tag 失败: ${RED}${TAG_FAIL} 个${NC}，已停止推送。"
    echo "=========================================="
    exit 1
fi

# ============================================
# 阶段 4: 推送到私有仓库
# ============================================
echo ""
echo "=========================================="
echo " 阶段 4/4: 推送到私有仓库 (${#ALL_IMAGES[@]} 个)"
echo "=========================================="

for image in "${ALL_IMAGES[@]}"; do
    push_image "$image"
done

# ============================================
# 汇总
# ============================================
echo ""
echo "=========================================="
echo -e " Pull: ${GREEN}${PULL_OK} 成功${NC}, ${YELLOW}${PULL_SKIP} 跳过${NC}, ${RED}${PULL_FAIL} 失败${NC}"
echo -e " Tag : ${GREEN}${TAG_OK} 成功${NC}, ${RED}${TAG_FAIL} 失败${NC}"
echo -e " Push: ${GREEN}${PUSH_OK} 成功${NC}, ${RED}${PUSH_FAIL} 失败${NC}"
echo "=========================================="

if ((PUSH_FAIL > 0)); then
    exit 1
fi
