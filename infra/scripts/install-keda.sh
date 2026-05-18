#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# KEDA Installation Script for KubeAI Platform
#
# Installs KEDA (Kubernetes Event-Driven Autoscaling) for
# inference service auto-scaling based on custom metrics.
#
# Prerequisites:
#   - Kubernetes 1.21+
#   - Helm 3.2+
#
# Usage:
#   ./install-keda.sh                  # Install with defaults
#   ./install-keda.sh --namespace keda  # Custom namespace
#   ./install-keda.sh --uninstall      # Remove KEDA
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[KEDA]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# -- Defaults
KEDA_NAMESPACE="keda"
UNINSTALL=false

# -- Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            KEDA_NAMESPACE="$2"
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
            echo "  --namespace NS    Installation namespace (default: ${KEDA_NAMESPACE})"
            echo "  --uninstall       Remove KEDA installation"
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
    log "Uninstalling KEDA..."
    helm uninstall keda -n "$KEDA_NAMESPACE" --ignore-not-found || true
    helm uninstall keda-add-ons-http -n "$KEDA_NAMESPACE" --ignore-not-found || true

    log "Waiting for resources to be cleaned up..."
    sleep 5

    REMAINING=$(kubectl get all -n "$KEDA_NAMESPACE" --ignore-not-found 2>/dev/null | wc -l)
    if [[ $REMAINING -le 0 ]]; then
        log "Deleting empty namespace '$KEDA_NAMESPACE'..."
        kubectl delete namespace "$KEDA_NAMESPACE" --ignore-not-found || true
    else
        warn "Namespace '$KEDA_NAMESPACE' still has resources. Manual cleanup may be needed."
    fi

    log "KEDA uninstalled successfully."
    exit 0
fi

# -- Install
log "Installing KEDA in namespace '${KEDA_NAMESPACE}'..."

# Add KEDA Helm repo if not present
if ! helm repo list | grep -q kedacore; then
    log "Adding KEDA Helm repository..."
    helm repo add kedacore https://kedacore.github.io/charts
    helm repo update
fi

# Create namespace if not exists
if ! kubectl get namespace "$KEDA_NAMESPACE" &>/dev/null; then
    log "Creating namespace '${KEDA_NAMESPACE}'..."
    kubectl create namespace "$KEDA_NAMESPACE"
fi

# Install KEDA core
log "Installing KEDA core..."
helm install keda kedacore/keda \
    --namespace "$KEDA_NAMESPACE" \
    --set installCRDs=true \
    --wait --timeout 5m

# Install KEDA HTTP add-on (for HTTP-based metrics scaling)
log "Installing KEDA HTTP add-on..."
helm install keda-add-ons-http kedacore/keda-add-ons-http \
    --namespace "$KEDA_NAMESPACE" \
    --wait --timeout 3m

# Verify installation
log "Verifying installation..."
OPERATOR_PODS=$(kubectl get pods -n "$KEDA_NAMESPACE" -l app=keda-operator --no-headers 2>/dev/null | wc -l)
METRICS_PODS=$(kubectl get pods -n "$KEDA_NAMESPACE" -l app=keda-operator-metrics-apiserver --no-headers 2>/dev/null | wc -l)

if [[ "$OPERATOR_PODS" -eq 0 ]]; then
    warn "KEDA operator pod not found. Check with: kubectl get pods -n ${KEDA_NAMESPACE}"
else
    log "KEDA operator is running (${OPERATOR_PODS} pod(s))."
    log "KEDA metrics-apiserver is running (${METRICS_PODS} pod(s))."
fi

# Create ClusterRole for KEDA to access pod metrics
log "Configuring RBAC for KEDA..."
kubectl apply -f - <<'RBAC' 2>/dev/null || true
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: keda-pod-reader
  labels:
    app.kubernetes.io/name: keda
    app.kubernetes.io/part-of: keda
rules:
- apiGroups: [""]
  resources: ["pods", "nodes"]
  verbs: ["get", "list", "watch"]
RBAC

echo ""
log "========================================="
log " KEDA installed successfully!"
log " Namespace: ${KEDA_NAMESPACE}"
log "========================================="
echo ""
log "Verify installation:"
echo "  kubectl get pods -n ${KEDA_NAMESPACE}"
echo "  kubectl get scaledobjects.keda.sh -A"
echo ""
log "Uninstall:"
echo "  $0 --uninstall --namespace ${KEDA_NAMESPACE}"