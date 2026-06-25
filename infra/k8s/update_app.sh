#!/bin/bash
# KubeAI - 按版本滚动升级前后端应用
# 用法: bash update_app.sh                 # 默认 latest
#       bash update_app.sh 0.2.0           # 升级到指定版本
#       bash update_app.sh rollback        # 回滚到上一次版本
#
# 前置条件:
#   1. 在生产节点上执行（需 root 权限）
#   2. kubectl 已配置集群访问
#   3. crictl 已配置私有仓库认证
#
# 升级流程:
#   1. 记录当前 Deployment 镜像版本（用于回滚）
#   2. crictl rmi + crictl pull 拉取指定版本镜像（crictl v1.29 不支持 --no-cache，
#      先清本地 tag 缓存再 pull 强制从远端拉最新 manifest 与 layer）
#   3. kubectl set image 显式更新 Deployment 模板到指定 tag
#   4. kubectl rollout restart 强制生成新 ReplicaSet（即便是 same tag + IfNotPresent
#      也会触发滚动，避免「远端 digest 已变但 crictl pull 走了缓存」导致 Pod 不刷新）
#   5. 逐个等待 rollout 就绪；scheduler 单串行避免重复调度
#   6. 超时则提示回滚命令

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REGISTRY="hub.uimpcloud.com/kubeai"
NAMESPACE="kubeai"
BACKEND_IMAGE_BASE="${REGISTRY}/kubeai-backend"
FRONTEND_IMAGE_BASE="${REGISTRY}/kubeai-frontend"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-180s}"

ACTION="${1:-}"
if [[ -z "${ACTION}" ]]; then
    ACTION="latest"
fi

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $*"; }

BACKEND_DEPLOYS=(
    "backend"
    "backend-taskiq-worker"
)
FRONTEND_DEPLOYS=(
    "frontend"
)
SCHEDULER_DEPLOY="backend-taskiq-scheduler"

# ============================================================
# 回滚模式
# ============================================================
if [[ "${ACTION}" == "rollback" ]]; then
    echo "=========================================="
    echo " KubeAI - 回滚 Deployment"
    echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
    for dep in "${BACKEND_DEPLOYS[@]}" "${FRONTEND_DEPLOYS[@]}" "${SCHEDULER_DEPLOY}"; do
        echo ""
        echo -e "  ${YELLOW}>>${NC} rollback ${dep}"
        if kubectl rollout undo "deployment/${dep}" -n "${NAMESPACE}"; then
            log_info "  [UNDO OK] ${dep}"
        else
            log_err "  [UNDO FAIL] ${dep}"
        fi
    done

    echo ""
    echo "=========================================="
    echo -e " ${GREEN}回滚已触发，等待各 Deployment 就绪...${NC}"
    echo "=========================================="
    for dep in "${BACKEND_DEPLOYS[@]}" "${FRONTEND_DEPLOYS[@]}" "${SCHEDULER_DEPLOY}"; do
        echo ""
        echo "  ${dep}..."
        if kubectl rollout status "deployment/${dep}" -n "${NAMESPACE}" --timeout="${ROLLOUT_TIMEOUT}"; then
            log_info "  [READY] ${dep}"
        else
            log_err "  [TIMEOUT] ${dep}"
        fi
    done
    exit 0
fi

VERSION="${ACTION}"
BACKEND_IMAGE="${BACKEND_IMAGE_BASE}:${VERSION}"
FRONTEND_IMAGE="${FRONTEND_IMAGE_BASE}:${VERSION}"

echo "=========================================="
echo " KubeAI - 按版本滚动升级"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 版本: ${VERSION}"
echo "=========================================="

# ============================================================
# 1. 记录升级前镜像版本（用于事后回滚）
# ============================================================
echo ""
echo -e "${YELLOW}>>> 记录升级前版本${NC}"
declare -A PREV_IMAGES
for dep in "${BACKEND_DEPLOYS[@]}" "${FRONTEND_DEPLOYS[@]}" "${SCHEDULER_DEPLOY}"; do
    img=$(kubectl get "deployment/${dep}" -n "${NAMESPACE}" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "")
    PREV_IMAGES["${dep}"]="${img}"
    echo "  ${dep}: ${img}"
done

# ============================================================
# 2. 拉取新版本镜像
# ============================================================
echo ""
echo -e "${YELLOW}>>> 拉取镜像${NC}"

# containerd 默认 pull 会复用本地 tag 缓存(本地 digest 与远端一致时跳过 layer 下载)。
# 但「IfNotPresent + 同 digest」会让 kubelet 直接用本地缓存镜像 — 即使你远端已经
# 重新 push 覆盖了 :latest tag, 节点本地仍然是 deploy 第一次拉的那份旧镜像,
# kubelet 不会重拉, Deployment Controller 也不会建新 RS, Pod 永远不会刷新。
#
# 解决: 先 rmi 清掉本地 tag 缓存(只清这一个 tag, 不影响其他镜像), 再 pull
# 此时本地无缓存, containerd 必须从远端完整拉 manifest + layer。
# crictl v1.29 不支持 --no-cache 标志 (那是 CRI-O / podman 的), 用 rmi+pull 兜底。

pull_image_fresh() {
    local image="$1"

    # 1. 清掉本地缓存(若存在)
    if crictl images --quiet "${image}" 2>/dev/null | grep -q .; then
        log_info "  [RMI]    ${image} (清掉本地缓存)"
        if ! crictl rmi "${image}" >/dev/null 2>&1; then
            log_warn "  [RMI FAIL] ${image} (继续尝试 pull)"
        fi
    fi

    # 2. 从远端完整拉取
    if ! crictl pull "${image}"; then
        log_err "拉取镜像失败: ${image}"
        return 1
    fi
    return 0
}

echo ""
echo "  [1/2] ${BACKEND_IMAGE}"
if ! pull_image_fresh "${BACKEND_IMAGE}"; then
    exit 1
fi
log_info "  [PULL OK] backend"

echo ""
echo "  [2/2] ${FRONTEND_IMAGE}"
if ! pull_image_fresh "${FRONTEND_IMAGE}"; then
    exit 1
fi
log_info "  [PULL OK] frontend"

# ============================================================
# 3. 滚动升级 Deployment（显式写入 tag，触发模板变更）
# ============================================================
echo ""
echo -e "${YELLOW}>>> 滚动升级 Deployment${NC}"

upgrade_deployment() {
    local dep="$1"
    local container="$2"
    local image="$3"

    echo ""
    echo -e "  ${YELLOW}>>${NC} ${dep} → ${image}"
    if ! kubectl set image "deployment/${dep}" "${container}=${image}" -n "${NAMESPACE}"; then
        log_err "  [SET IMAGE FAIL] ${dep}"
        return 1
    fi
    log_info "  [SET IMAGE OK] ${dep}"

    # 同 tag + imagePullPolicy=IfNotPresent 时, kubelet 看到本地缓存 digest 与
    # 远端一致会跳过 pull, Deployment Controller 也不会生成新 ReplicaSet。
    # 即便上面 crictl pull --no-cache 已经把新 layer 拉到节点本地, 显式 restart
    # 才能让 K8s 立刻生成新 RS 走完整滚动流程, 避免「远端已更新、Pod 还在用旧镜像」。
    echo -e "  ${YELLOW}>>${NC} rollout restart ${dep}"
    if ! kubectl rollout restart "deployment/${dep}" -n "${NAMESPACE}"; then
        log_err "  [RESTART FAIL] ${dep}"
        return 1
    fi
    log_info "  [RESTART OK] ${dep}"
    return 0
}

for dep in "${BACKEND_DEPLOYS[@]}"; do
    if [[ "${dep}" == "backend-taskiq-worker" ]]; then
        upgrade_deployment "${dep}" "taskiq-worker" "${BACKEND_IMAGE}" || exit 1
    else
        upgrade_deployment "${dep}" "backend" "${BACKEND_IMAGE}" || exit 1
    fi
done
for dep in "${FRONTEND_DEPLOYS[@]}"; do
    upgrade_deployment "${dep}" "frontend" "${FRONTEND_IMAGE}" || exit 1
done

# ============================================================
# 4. 等待 backend / worker / frontend 就绪
# ============================================================
echo ""
echo -e "${YELLOW}>>> 等待 Pod 就绪${NC}"
WAIT_OK=0
WAIT_FAIL=0
FAILED_DEPLOYS=()

wait_deploy() {
    local dep="$1"
    echo ""
    echo "  ${dep}..."
    if kubectl rollout status "deployment/${dep}" -n "${NAMESPACE}" --timeout="${ROLLOUT_TIMEOUT}"; then
        log_info "  [READY] ${dep}"
        return 0
    else
        log_err "  [TIMEOUT] ${dep}"
        return 1
    fi
}

for dep in "${BACKEND_DEPLOYS[@]}" "${FRONTEND_DEPLOYS[@]}"; do
    if wait_deploy "${dep}"; then
        WAIT_OK=$((WAIT_OK + 1))
    else
        WAIT_FAIL=$((WAIT_FAIL + 1))
        FAILED_DEPLOYS+=("${dep}")
    fi
done

# ============================================================
# 5. 单独滚动 scheduler（必须单串行）
# ============================================================
echo ""
echo -e "${YELLOW}>>> 滚动升级 Taskiq Scheduler（单串行）${NC}"
if upgrade_deployment "${SCHEDULER_DEPLOY}" "taskiq-scheduler" "${BACKEND_IMAGE}"; then
    if wait_deploy "${SCHEDULER_DEPLOY}"; then
        WAIT_OK=$((WAIT_OK + 1))
    else
        WAIT_FAIL=$((WAIT_FAIL + 1))
        FAILED_DEPLOYS+=("${SCHEDULER_DEPLOY}")
    fi
else
    WAIT_FAIL=$((WAIT_FAIL + 1))
    FAILED_DEPLOYS+=("${SCHEDULER_DEPLOY}")
fi

# ============================================================
# 6. 汇总
# ============================================================
echo ""
echo "=========================================="
if [[ ${WAIT_FAIL} -eq 0 ]]; then
    echo -e " ${GREEN}升级完成 (${WAIT_OK} 个组件)${NC}"
    echo ""
    echo " 新版本:"
    echo "   backend:                    ${BACKEND_IMAGE}"
    echo "   backend-taskiq-worker:      ${BACKEND_IMAGE}"
    echo "   backend-taskiq-scheduler:   ${BACKEND_IMAGE}"
    echo "   frontend:                   ${FRONTEND_IMAGE}"
    echo ""
    echo " 如需回滚:"
    echo "   bash update_app.sh rollback"
else
    log_err "升级完成，但 ${WAIT_FAIL} 个组件未就绪: ${FAILED_DEPLOYS[*]}"
    echo ""
    echo " 升级前版本（记录在上方）:"
    for dep in "${FAILED_DEPLOYS[@]}"; do
        echo "   ${dep}: ${PREV_IMAGES[${dep}]}"
    done
    echo ""
    echo " 可执行以下命令回滚:"
    echo "   bash update_app.sh rollback"
    echo ""
    echo " 或手动回滚单个组件:"
    for dep in "${FAILED_DEPLOYS[@]}"; do
        echo "   kubectl rollout undo deployment/${dep} -n ${NAMESPACE}"
    done
    exit 1
fi
echo "=========================================="