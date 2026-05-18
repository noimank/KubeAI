#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Volcano Installation Script for KubeAI Platform
#
# Installs Volcano batch scheduler for training job management.
#
# Prerequisites:
#   - Kubernetes 1.19+
#   - Helm 3.2+
#
# Usage:
#   ./install-volcano.sh                  # Install with defaults
#   ./install-volcano.sh --namespace volcano-system  # Custom namespace
#   ./install-volcano.sh --uninstall      # Remove Volcano
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[Volcano]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# -- Defaults
VOLCANO_NAMESPACE="volcano-system"
UNINSTALL=false

# -- Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            VOLCANO_NAMESPACE="$2"
            shift 2
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --namespace NS    Installation namespace (default: ${VOLCANO_NAMESPACE})"
            echo "  --uninstall       Remove Volcano installation"
            echo "  --help            Show this help message"
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

# Check kubectl cluster access
if ! kubectl cluster-info &>/dev/null; then
    err "Cannot access Kubernetes cluster. Check your kubeconfig."
    exit 1
fi

# -- Uninstall
if [[ "$UNINSTALL" == true ]]; then
    log "Uninstalling Volcano..."
    helm uninstall volcano -n "$VOLCANO_NAMESPACE" --ignore-not-found || true

    log "Waiting for resources to be cleaned up..."
    sleep 5

    REMAINING=$(kubectl get all -n "$VOLCANO_NAMESPACE" --ignore-not-found 2>/dev/null | wc -l)
    if [[ $REMAINING -le 0 ]]; then
        log "Deleting empty namespace '$VOLCANO_NAMESPACE'..."
        kubectl delete namespace "$VOLCANO_NAMESPACE" --ignore-not-found || true
    else
        warn "Namespace '$VOLCANO_NAMESPACE' still has resources. Manual cleanup may be needed."
    fi

    log "Volcano uninstalled successfully."
    exit 0
fi

# -- Install
log "Installing Volcano in namespace '${VOLCANO_NAMESPACE}'..."

# Add Volcano Helm repo if not present
if ! helm repo list | grep -q volcano-sh; then
    log "Adding Volcano Helm repository..."
    helm repo add volcano-sh https://volcano-sh.github.io/helm-charts
    helm repo update
fi

# Create namespace if not exists
if ! kubectl get namespace "$VOLCANO_NAMESPACE" &>/dev/null; then
    log "Creating namespace '${VOLCANO_NAMESPACE}'..."
    kubectl create namespace "$VOLCANO_NAMESPACE"
fi

# Install Volcano
log "Installing Volcano Helm chart..."
helm install volcano volcano-sh/volcano \
    --namespace "$VOLCANO_NAMESPACE" \
    --set scheduler.enableJobHistory=true \
    --set scheduler.replicaCount=1 \
    --set controller.replicaCount=1 \
    --wait --timeout 5m

# Verify installation
log "Verifying installation..."
CONTROLLER_PODS=$(kubectl get pods -n "$VOLCANO_NAMESPACE" -l app=volcano-controller --no-headers 2>/dev/null | wc -l)
SCHEDULER_PODS=$(kubectl get pods -n "$VOLCANO_NAMESPACE" -l app=volcano-scheduler --no-headers 2>/dev/null | wc -l)

if [[ "$CONTROLLER_PODS" -eq 0 ]] || [[ "$SCHEDULER_PODS" -eq 0 ]]; then
    warn "Some Volcano pods are not running. Check with: kubectl get pods -n ${VOLCANO_NAMESPACE}"
else
    log "Volcano controller is running (${CONTROLLER_PODS} pod(s))."
    log "Volcano scheduler is running (${SCHEDULER_PODS} pod(s))."
fi

# Create default Queue
log "Creating default Queue..."
kubectl apply -f - <<'QUEUE' 2>/dev/null || true
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
metadata:
  name: default
spec:
  weight: 1
  capability:
    cpu: 100
    memory: 100Gi
QUEUE

echo ""
log "========================================="
log " Volcano installed successfully!"
log " Namespace: ${VOLCANO_NAMESPACE}"
log "========================================="
echo ""
log "Verify installation:"
echo "  kubectl get pods -n ${VOLCANO_NAMESPACE}"
echo "  kubectl get queue"
echo ""
log "Uninstall:"
echo "  $0 --uninstall --namespace ${VOLCANO_NAMESPACE}"