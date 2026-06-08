#!/bin/bash
# KServe 推理链路 — 部署 Istio + Gateway (纯 kubectl apply，无需 istioctl)
# 用法: bash infra/k8s/kserve/istio/install.sh
#
# 离线部署准备:
#   1. 在有网机器上运行 generate.sh 生成 istio-manifest.yaml
#   2. 将镜像推送到私有仓库: PRIVATE_REGISTRY=your-registry bash generate.sh
#   3. 提交生成的 istio-manifest.yaml 到仓库
#
# 目标集群上执行本脚本:
#   bash infra/k8s/kserve/istio/install.sh
#
# 如集群已有 Istio，仅部署 Gateway:
#   SKIP_ISTIO=1 bash infra/k8s/kserve/istio/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ISTIO_MANIFEST="$SCRIPT_DIR/istio-manifest.yaml"
GATEWAY_FILE="$SCRIPT_DIR/kserve-gateway.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; }

echo ""
echo "=========================================="
echo " KServe 推理链路 — Istio + Gateway 部署"
echo " 纯 kubectl apply，无需 istioctl"
echo "=========================================="
echo ""

# ============================================================
# 0. 检查前置条件
# ============================================================
log "检查 kubectl..."
if ! command -v kubectl &>/dev/null; then
    err "kubectl 未找到"
    exit 1
fi
if ! kubectl cluster-info &>/dev/null; then
    err "无法连接 Kubernetes 集群"
    exit 1
fi
log "集群连接正常"

# ============================================================
# 1. 检查是否已有 Istio
# ============================================================
HAS_ISTIO=false
if kubectl get namespace istio-system --no-headers &>/dev/null && \
   kubectl get pods -n istio-system -l istio=ingressgateway --no-headers 2>/dev/null | grep -q Running; then
    HAS_ISTIO=true
    warn "istio-system 中已有运行中的 Istio"
fi

# ============================================================
# 2. 部署 Istio
# ============================================================
install_istio() {
    if [[ "${SKIP_ISTIO:-0}" == "1" ]]; then
        log "SKIP_ISTIO=1，跳过 Istio 部署"
        return
    fi
    if $HAS_ISTIO; then
        log "Istio 已存在，跳过部署"
        return
    fi

    if [[ ! -f "$ISTIO_MANIFEST" ]]; then
        err "Istio manifest 文件不存在: $ISTIO_MANIFEST"
        err ""
        err "请先在有网机器上生成:"
        err "  bash infra/k8s/kserve/istio/generate.sh"
        err ""
        err "如需私有仓库，指定 PRIVATE_REGISTRY:"
        err "  PRIVATE_REGISTRY=hub.uimpcloud.com/kubeai bash infra/k8s/kserve/istio/generate.sh"
        exit 1
    fi

    if [[ -n "${PRIVATE_REGISTRY:-}" ]]; then
        log "使用私有仓库: $PRIVATE_REGISTRY"
        local patched
        patched="$(mktemp /tmp/istio-manifest-patched.XXXXXX.yaml)"
        trap "rm -f $patched" EXIT
        sed "s|docker.io/istio|${PRIVATE_REGISTRY}/istio|g" "$ISTIO_MANIFEST" > "$patched"
        log "部署 Istio (kubectl apply, 镜像源: ${PRIVATE_REGISTRY}/istio)..."
        kubectl apply -f "$patched"
    else
        log "部署 Istio (kubectl apply)..."
        kubectl apply -f "$ISTIO_MANIFEST"
    fi

    log "等待 istio-ingressgateway Pod 就绪 (最多 120s)..."
    kubectl wait --for=condition=ready pod \
        -l istio=ingressgateway \
        -n istio-system \
        --timeout=120s || {
        warn "istio-ingressgateway 未就绪，请检查:"
        warn "  kubectl get pods -n istio-system"
        warn "  kubectl describe pod -n istio-system -l istio=ingressgateway"
    }

    echo ""
    log "Istio 组件状态:"
    kubectl get pods -n istio-system
    echo ""
    kubectl get svc -n istio-system
}

# ============================================================
# 3. 创建 KServe Gateway + IngressClass
# ============================================================
apply_gateway() {
    kubectl create namespace kserve --dry-run=client -o yaml | kubectl apply -f -

    log "创建 KServe Gateway + IngressClass..."
    kubectl apply -f "$GATEWAY_FILE"

    echo ""
    log "验证:"
    echo -n "  IngressClass: "
    kubectl get ingressclass istio -o jsonpath='{.spec.controller}' 2>/dev/null && echo "" || echo "未创建"
    echo -n "  Gateway:      "
    kubectl get gateway kserve-ingress-gateway -n kserve -o jsonpath='{.metadata.name}' 2>/dev/null && echo "" || echo "未创建"
}

# ============================================================
# 4. 执行
# ============================================================
install_istio
apply_gateway

echo ""
echo "=========================================="
echo -e " ${GREEN}部署完成${NC}"
echo ""
echo " 推理服务入站链路:"
echo "   外部请求 → istio-ingressgateway → VirtualService → 推理 Pod"
echo ""
echo " 本地测试:"
echo "   kubectl port-forward -n istio-system svc/istio-ingressgateway 8080:80"
echo "   curl http://localhost:8080/v1/models/<inference-name>:predict"
echo ""
echo " 生产访问 (获取 NodePort/LB 地址):"
echo "   kubectl get svc istio-ingressgateway -n istio-system"
echo "=========================================="
