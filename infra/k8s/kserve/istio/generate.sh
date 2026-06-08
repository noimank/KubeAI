#!/bin/bash
# 生成 Istio 纯 K8s YAML manifest
# 用法: bash infra/k8s/kserve/istio/generate.sh
#
# 该脚本在有网机器上执行一次，生成 istio-manifest.yaml 后提交到仓库。
# 目标集群只需 kubectl apply，不需要 istioctl。
#
# 环境变量:
#   ISTIO_VERSION      - Istio 版本 (默认 1.24.3)
#   PRIVATE_REGISTRY   - 私有仓库前缀 (离线环境必填)
#                        例如 PRIVATE_REGISTRY=hub.uimpcloud.com/kubeai
#
# 输出: infra/k8s/kserve/istio/istio-manifest.yaml

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ISTIO_VERSION="${ISTIO_VERSION:-1.24.3}"
OPERATOR_FILE="$SCRIPT_DIR/istio-operator.yaml"
OUTPUT_FILE="$SCRIPT_DIR/istio-manifest.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; }

# ============================================================
# 1. 查找 istioctl (本地 → PATH → Docker)
# ============================================================
find_istioctl() {
    if [[ -n "${ISTIOCTL:-}" ]] && [[ -x "$ISTIOCTL" ]]; then
        echo "istioctl" "$ISTIOCTL"
        return 0
    fi
    if command -v istioctl &>/dev/null; then
        echo "istioctl" "$(command -v istioctl)"
        return 0
    fi
    local bin="$HOME/.istioctl/bin/istioctl"
    if [[ -x "$bin" ]]; then
        echo "istioctl" "$bin"
        return 0
    fi
    return 1
}

USE_DOCKER=false
ISTIOCTL_BIN=""

if found=$(find_istioctl); then
    ISTIOCTL_BIN=$(echo "$found" | awk '{print $2}')
    log "istioctl: $ISTIOCTL_BIN"
else
    # 检查 Docker 是否可用
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        log "使用 Docker 运行 istioctl (本地无 istioctl 二进制)"
        USE_DOCKER=true
    else
        # 尝试下载
        log "下载 Istio ${ISTIO_VERSION}..."
        ISTIO_DIR="$HOME/.istioctl"
        mkdir -p "$ISTIO_DIR"

        OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
        ARCH="$(uname -m)"
        case "$ARCH" in
            x86_64)  ARCH="amd64" ;;
            aarch64) ARCH="arm64" ;;
        esac

        TARBALL="istio-${ISTIO_VERSION}-${OS}-${ARCH}.tar.gz"
        URL="https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/${TARBALL}"

        if command -v curl &>/dev/null; then
            curl -sSL "$URL" -o "/tmp/$TARBALL"
        elif command -v wget &>/dev/null; then
            wget -q "$URL" -O "/tmp/$TARBALL"
        else
            err "无法下载 istioctl (无 curl/wget)，且 Docker 不可用"
            exit 1
        fi

        tar -xzf "/tmp/$TARBALL" -C "$ISTIO_DIR" --strip-components=1
        rm -f "/tmp/$TARBALL"
        ISTIOCTL_BIN="$ISTIO_DIR/bin/istioctl"

        if ! "$ISTIOCTL_BIN" version &>/dev/null 2>&1; then
            err "istioctl 无法运行 (可能平台不匹配)，尝试 Docker 方式..."
            if command -v docker &>/dev/null; then
                USE_DOCKER=true
            else
                err "Docker 也不可用，请手动安装 istioctl"
                exit 1
            fi
        else
            log "istioctl 已下载到 $ISTIOCTL_BIN"
        fi
    fi
fi

# ============================================================
# 2. 处理私有仓库
# ============================================================
MANIFEST_OPERATOR="$OPERATOR_FILE"
if [[ -n "${PRIVATE_REGISTRY:-}" ]]; then
    log "替换镜像仓库: docker.io/istio → ${PRIVATE_REGISTRY}/istio"
    MANIFEST_OPERATOR="$(mktemp /tmp/istio-operator-patched.XXXXXX.yaml)"
    sed "s|^  hub: docker.io/istio|  hub: ${PRIVATE_REGISTRY}/istio|" \
        "$OPERATOR_FILE" > "$MANIFEST_OPERATOR"
fi

# ============================================================
# 3. 生成 manifest
# ============================================================
log "生成 Istio manifest..."
if $USE_DOCKER; then
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    # Windows Git Bash 需要 MSYS_NO_PATHCONV=1 防止路径转换
    if [[ "$(uname -s)" == MINGW* ]] || [[ "$(uname -s)" == MSYS* ]]; then
        MSYS_NO_PATHCONV=1 docker run --rm \
            -v "${REPO_ROOT}":/work \
            "docker.io/istio/istioctl:${ISTIO_VERSION}" \
            manifest generate -f /work/infra/k8s/kserve/istio/istio-operator.yaml > "$OUTPUT_FILE"
    else
        docker run --rm \
            -v "${REPO_ROOT}":/work \
            "docker.io/istio/istioctl:${ISTIO_VERSION}" \
            manifest generate -f /work/infra/k8s/kserve/istio/istio-operator.yaml > "$OUTPUT_FILE"
    fi
else
    "$ISTIOCTL_BIN" manifest generate -f "$MANIFEST_OPERATOR" > "$OUTPUT_FILE"
fi

log "已生成: $OUTPUT_FILE"
log "行数: $(wc -l < "$OUTPUT_FILE")"
log ""
log "下一步: 将 istio-manifest.yaml 提交到仓库，目标集群上执行:"
log "  kubectl apply -f $OUTPUT_FILE"

# 清理临时文件
if [[ "$MANIFEST_OPERATOR" != "$OPERATOR_FILE" ]]; then
    rm -f "$MANIFEST_OPERATOR"
fi
