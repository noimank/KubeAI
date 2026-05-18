#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Development Environment Setup for KubeAI Platform
#
# Installs:
#   - Infrastructure via Helm (PostgreSQL, Redis, MinIO, Harbor, etc.)
#   - Backend dependencies and migrations
#   - Frontend dependencies
#   - Kubernetes components (Volcano, KEDA, KServe) for dev cluster
#
# Prerequisites:
#   - Kubernetes cluster (kind, minikube, etc.)
#   - Helm 3.8+
#   - uv (Python package manager)
#   - pnpm (Node.js package manager)
#
# Usage:
#   ./dev-setup.sh              # Full setup
#   ./dev-setup.sh --k8s-only   # Only K8s components (skip Docker/backend/frontend)
#   ./dev-setup.sh --help       # Show help
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[KubeAI]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# -- Defaults
K8S_ONLY=false

# -- Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --k8s-only)
            K8S_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --k8s-only   Only install K8s components (skip Docker/backend/frontend)"
            echo "  --help       Show this help message"
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            exit 1
            ;;
    esac
done

# -- Check prerequisites
check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        warn "$1 not found. Please install it first."
        return 1
    fi
    return 0
}

check_in_cluster() {
    if kubectl cluster-info &>/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# -- Install K8s components only
install_k8s_components() {
    log "Installing K8s components..."

    # Volcano (job scheduling for training)
    if ! kubectl get namespace volcano-system &>/dev/null 2>&1; then
        log "Installing Volcano..."
        bash "$SCRIPT_DIR/install-volcano.sh"
    else
        log "Volcano already installed, skipping."
    fi

    # KEDA (auto-scaling for inference services)
    if ! kubectl get namespace keda &>/dev/null 2>&1; then
        log "Installing KEDA..."
        bash "$SCRIPT_DIR/install-keda.sh"
    else
        log "KEDA already installed, skipping."
    fi

    # KServe (model serving)
    if ! kubectl get namespace kserve &>/dev/null 2>&1; then
        log "Installing KServe..."
        bash "$SCRIPT_DIR/install-kserve.sh"
    else
        log "KServe already installed, skipping."
    fi

    log "K8s components installation complete."
}

# -- Full setup (Helm + local dev)
if [[ "$K8S_ONLY" == false ]]; then
    log "Checking prerequisites..."
    MISSING=0
    for cmd in helm kubectl uv pnpm; do
        if ! check_cmd "$cmd"; then MISSING=1; fi
    done
    if [ $MISSING -eq 1 ]; then
        echo "Install missing tools and re-run this script."
        exit 1
    fi

    # -- Deploy infrastructure via Helm
    if check_in_cluster; then
        HELM_VALUES="$PROJECT_ROOT/infra/helm/kubeai/values-dev.yaml"
        if [ ! -f "$HELM_VALUES" ]; then
            warn "values-dev.yaml not found. Skipping Helm deployment."
        else
            log "Deploying PostgreSQL, Redis, MinIO via Helm..."
            helm upgrade --install kubeai "$PROJECT_ROOT/infra/helm/kubeai/" \
                -f "$HELM_VALUES" \
                -n kubeai --create-namespace
            log "Helm deployment complete."
        fi
    else
        warn "No Kubernetes cluster detected. Skipping Helm deployment."
    fi

    # -- Backend setup
    log "Setting up backend..."
    cd "$PROJECT_ROOT/backend"

    if [ ! -f .env ]; then
        cp .env.example .env
        log "Created .env from .env.example"
    fi

    uv sync
    log "Backend dependencies installed."

    uv run alembic upgrade head
    log "Database migrations applied."

    # -- Frontend setup
    log "Setting up frontend..."
    cd "$PROJECT_ROOT/frontend"
    pnpm install
    log "Frontend dependencies installed."

    # -- Install K8s components if cluster is available
    if check_in_cluster; then
        install_k8s_components
    else
        warn "No Kubernetes cluster detected. Skipping K8s components."
    fi

    # -- Done
    echo ""
    log "========================================="
    log " Development environment is ready!"
    log "========================================="
    echo ""
    log "Start backend:"
    echo "  cd backend && uv run uvicorn app.main:app --reload"
    echo ""
    log "Start frontend:"
    echo "  cd frontend && pnpm dev"
    echo ""

else
    # -- K8s components only
    log "========================================="
    log " Installing K8s components only"
    log "========================================="

    if ! check_in_cluster; then
        err "Cannot access Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi

    install_k8s_components

    echo ""
    log "========================================="
    log " K8s components installation complete!"
    log "========================================="
    echo ""
    log "Next steps:"
    echo "  - Start backend: cd backend && uv run uvicorn app.main:app --reload"
    echo "  - Start frontend: cd frontend && pnpm dev"
    echo ""
fi

log "Verify K8s components:"
echo "  kubectl get pods -n volcano-system"
echo "  kubectl get pods -n keda"
echo "  kubectl get pods -n kserve"
echo "  kubectl get clusterservingruntimes"
