#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Production/Infrastructure Setup for KubeAI Platform
#
# Installs all K8s infrastructure components required for
# production deployment.
#
# Components:
#   - cert-manager (TLS certificates for KServe webhooks)
#   - Volcano (job scheduling for training jobs)
#   - KEDA (auto-scaling for inference services)
#   - KServe (model serving infrastructure)
#
# Prerequisites:
#   - Kubernetes 1.28+
#   - Helm 3.8+
#   - kubectl configured with cluster access
#
# Usage:
#   ./setup-infra.sh              # Interactive setup (installs all)
#   ./setup-infra.sh --all        # Non-interactive (all components)
#   ./setup-infra.sh --cert-manager  # Only cert-manager
#   ./setup-infra.sh --volcano       # Only Volcano
#   ./setup-infra.sh --keda         # Only KEDA
#   ./setup-infra.sh --kserve       # Only KServe
#   ./setup-infra.sh --uninstall    # Remove all components
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[KubeAI-Infra]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# -- Defaults
INSTALL_ALL=false
UNINSTALL=false
COMPONENTS=""

# -- Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            INSTALL_ALL=true
            shift
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --cert-manager|--volcano|--keda|--kserve)
            COMPONENTS="$COMPONENTS ${1#--}"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all           Install all infrastructure components"
            echo "  --cert-manager  Only install cert-manager"
            echo "  --volcano       Only install Volcano"
            echo "  --keda          Only install KEDA"
            echo "  --kserve        Only install KServe"
            echo "  --uninstall     Remove all components"
            echo "  --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --all                # Install everything"
            echo "  $0 --volcano --keda     # Install only Volcano and KEDA"
            echo "  $0 --uninstall          # Remove all components"
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
        err "$1 is required but not found. Please install it first."
        return 1
    fi
    return 0
}

log "Checking prerequisites..."
for cmd in helm kubectl; do
    if ! check_cmd "$cmd"; then exit 1; fi
done

if ! kubectl cluster-info &>/dev/null; then
    err "Cannot access Kubernetes cluster. Check your kubeconfig."
    exit 1
fi

ensure_cert_manager() {
    if kubectl get namespace cert-manager &>/dev/null 2>&1; then
        log "cert-manager already installed, skipping."
        return
    fi

    log "Installing cert-manager..."
    helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
    helm repo update jetstack
    helm install cert-manager jetstack/cert-manager \
        --namespace cert-manager \
        --create-namespace \
        --set crds.enabled=true \
        --wait
    log "cert-manager installed."
}

# -- Uninstall all
uninstall_all() {
    log "Removing all KubeAI infrastructure components..."

    log "Removing KServe..."
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/kserve/kserve-cluster-resources.yaml" --ignore-not-found 2>/dev/null || true
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/kserve/kserve.yaml" --ignore-not-found 2>/dev/null || true
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/kserve/kserve-crd.yaml" --ignore-not-found 2>/dev/null || true
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/kserve/00-namespace.yaml" --ignore-not-found 2>/dev/null || true

    log "Removing KEDA..."
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/keda/keda.yaml" --ignore-not-found 2>/dev/null || true
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/keda/00-namespace.yaml" --ignore-not-found 2>/dev/null || true

    log "Removing Volcano..."
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/volcano/99-default-queue.yaml" --ignore-not-found 2>/dev/null || true
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/volcano/volcano.yaml" --ignore-not-found 2>/dev/null || true
    kubectl delete -f "$PROJECT_ROOT/infra/k8s/volcano/00-namespace.yaml" --ignore-not-found 2>/dev/null || true

    log "Removing cert-manager..."
    helm uninstall cert-manager -n cert-manager --ignore-not-found 2>/dev/null || true
    kubectl delete namespace cert-manager --ignore-not-found 2>/dev/null || true

    log "All components removed."
}

# -- Main logic
if [[ "$UNINSTALL" == true ]]; then
    uninstall_all
    exit 0
fi

if [[ "$INSTALL_ALL" == true ]]; then
    COMPONENTS="cert-manager volcano keda kserve"
fi

if [[ -z "$COMPONENTS" ]]; then
    echo "Select components to install:"
    echo "  [1] All components (cert-manager, Volcano, KEDA, KServe)"
    echo "  [2] cert-manager only"
    echo "  [3] Volcano only (training job scheduling)"
    echo "  [4] KEDA only (inference auto-scaling)"
    echo "  [5] KServe only (model serving)"
    echo "  [Q] Quit"
    echo ""
    read -p "Select option [1]: " choice

    case "$choice" in
        1|"") COMPONENTS="cert-manager volcano keda kserve" ;;
        2) COMPONENTS="cert-manager" ;;
        3) COMPONENTS="volcano" ;;
        4) COMPONENTS="keda" ;;
        5) COMPONENTS="kserve" ;;
        Q|q) exit 0 ;;
        *) err "Invalid option: $choice"; exit 1 ;;
    esac
fi

log "========================================="
log " Installing KubeAI Infrastructure"
log " Components: $COMPONENTS"
log "========================================="

# Install cert-manager first (required by KServe)
if [[ "$COMPONENTS" == *"cert-manager"* ]]; then
    ensure_cert_manager
fi

# Install Volcano
if [[ "$COMPONENTS" == *"volcano"* ]]; then
    log "Installing Volcano..."
    kubectl apply -f "$PROJECT_ROOT/infra/k8s/volcano/00-namespace.yaml"
    kubectl apply -f "$PROJECT_ROOT/infra/k8s/volcano/volcano.yaml"
    kubectl wait --for=condition=Established --timeout=60s crd/jobs.batch.volcano.sh crd/queues.scheduling.volcano.sh
    kubectl apply -f "$PROJECT_ROOT/infra/k8s/volcano/99-default-queue.yaml"
fi

# Install KEDA
if [[ "$COMPONENTS" == *"keda"* ]]; then
    log "Installing KEDA..."
    kubectl apply -f "$PROJECT_ROOT/infra/k8s/keda/00-namespace.yaml"
    kubectl apply --server-side -f "$PROJECT_ROOT/infra/k8s/keda/keda.yaml"
fi

# Install KServe (depends on cert-manager)
if [[ "$COMPONENTS" == *"kserve"* ]]; then
    ensure_cert_manager
    log "Installing KServe..."
    kubectl apply -f "$PROJECT_ROOT/infra/k8s/kserve/00-namespace.yaml"
    kubectl apply --server-side -f "$PROJECT_ROOT/infra/k8s/kserve/kserve-crd.yaml"
    kubectl wait --for=condition=Established --timeout=60s \
        crd/inferenceservices.serving.kserve.io \
        crd/servingruntimes.serving.kserve.io \
        crd/clusterservingruntimes.serving.kserve.io
    kubectl apply -f "$PROJECT_ROOT/infra/k8s/kserve/kserve.yaml"
    kubectl apply --server-side -f "$PROJECT_ROOT/infra/k8s/kserve/kserve-cluster-resources.yaml"
fi

echo ""
log "========================================="
log " Infrastructure setup complete!"
log "========================================="
echo ""
log "Verify installation:"
echo "  kubectl get pods -n cert-manager"
echo "  kubectl get pods -n volcano-system"
echo "  kubectl get pods -n keda"
echo "  kubectl get pods -n kserve"
echo "  kubectl get clusterservingruntimes"
