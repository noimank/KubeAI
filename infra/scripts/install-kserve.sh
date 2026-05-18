#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# KServe Installation Script for KubeAI Platform
#
# Installs KServe using official Helm OCI charts in
# Standard (RawDeployment) mode — no Knative Serving required.
#
# Prerequisites:
#   - Kubernetes 1.32+
#   - Helm 3.8+ (OCI support)
#   - Cert Manager 1.15+ (auto-installed if not present)
#
# Usage:
#   ./install-kserve.sh                          # Install with defaults
#   ./install-kserve.sh --version v0.17.0        # Specific version
#   ./install-kserve.sh --skip-cert-manager      # Skip cert-manager install
#   ./install-kserve.sh --uninstall               # Remove KServe
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[KServe]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# -- Defaults
KSERVE_VERSION="v0.17.0"
KSERVE_NAMESPACE="kserve"
DEPLOYMENT_MODE="Standard"
UNINSTALL=false
SKIP_CERT_MANAGER=false
ENABLE_INGRESS=true
OCI_REGISTRY="oci://ghcr.io/kserve/charts"

# -- Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            KSERVE_VERSION="$2"
            shift 2
            ;;
        --namespace)
            KSERVE_NAMESPACE="$2"
            shift 2
            ;;
        --mode)
            DEPLOYMENT_MODE="$2"
            shift 2
            ;;
        --skip-cert-manager)
            SKIP_CERT_MANAGER=true
            shift
            ;;
        --no-ingress)
            ENABLE_INGRESS=false
            shift
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --version VERSION       KServe chart version (default: ${KSERVE_VERSION})"
            echo "  --namespace NS          Installation namespace (default: ${KSERVE_NAMESPACE})"
            echo "  --mode MODE             Deployment mode: Standard or Knative (default: ${DEPLOYMENT_MODE})"
            echo "  --skip-cert-manager     Skip cert-manager installation"
            echo "  --no-ingress            Disable ingress gateway"
            echo "  --uninstall             Remove KServe installation"
            echo "  --help                  Show this help message"
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

# Check Helm version (need 3.8+ for OCI support)
HELM_MAJOR=$(helm version --template '{{ .Version }}' | cut -d. -f1 | tr -d 'v')
HELM_MINOR=$(helm version --template '{{ .Version }}' | cut -d. -f2)
if [[ "$HELM_MAJOR" -lt 3 ]] || { [[ "$HELM_MAJOR" -eq 3 ]] && [[ "$HELM_MINOR" -lt 8 ]]; }; then
    err "Helm 3.8+ is required for OCI registry support. Current: $(helm version --short)"
    exit 1
fi

# Check kubectl cluster access
if ! kubectl cluster-info &>/dev/null; then
    err "Cannot access Kubernetes cluster. Check your kubeconfig."
    exit 1
fi

# -- Uninstall
if [[ "$UNINSTALL" == true ]]; then
    log "Uninstalling KServe..."
    helm uninstall kserve -n "$KSERVE_NAMESPACE" --ignore-not-found || true
    helm uninstall kserve-crd -n "$KSERVE_NAMESPACE" --ignore-not-found || true

    log "Waiting for resources to be cleaned up..."
    sleep 5

    # Check if namespace is empty and offer to delete
    REMAINING=$(kubectl get all -n "$KSERVE_NAMESPACE" --ignore-not-found 2>/dev/null | wc -l)
    if [[ "$REMAINING" -le 0 ]]; then
        log "Deleting empty namespace '$KSERVE_NAMESPACE'..."
        kubectl delete namespace "$KSERVE_NAMESPACE" --ignore-not-found || true
    else
        warn "Namespace '$KSERVE_NAMESPACE' still has resources. Manual cleanup may be needed."
    fi

    log "KServe uninstalled successfully."
    exit 0
fi

# -- Install
log "Installing KServe ${KSERVE_VERSION} in ${DEPLOYMENT_MODE} mode..."
log "Target namespace: ${KSERVE_NAMESPACE}"

# Step 0: Install cert-manager if not present
if [[ "$SKIP_CERT_MANAGER" == false ]]; then
    if ! kubectl get namespace cert-manager &>/dev/null; then
        log "Installing cert-manager (required for KServe webhook certs)..."
        helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
        helm repo update jetstack
        helm install cert-manager jetstack/cert-manager \
            --namespace cert-manager \
            --create-namespace \
            --set crds.enabled=true \
            --wait
        log "cert-manager installed."
    else
        log "cert-manager already installed, skipping."
    fi
fi

# Create namespace
if ! kubectl get namespace "$KSERVE_NAMESPACE" &>/dev/null; then
    log "Creating namespace '${KSERVE_NAMESPACE}'..."
    kubectl create namespace "$KSERVE_NAMESPACE"
fi

# Step 1: Install CRDs
log "Installing KServe CRDs..."
helm install kserve-crd "${OCI_REGISTRY}/kserve-crd" \
    --version "$KSERVE_VERSION" \
    --namespace "$KSERVE_NAMESPACE" \
    --wait

log "CRDs installed. Waiting for API registration..."
for i in $(seq 1 60); do
    if kubectl get crd inferenceservices.serving.kserve.io &>/dev/null; then
        break
    fi
    sleep 2
done

if ! kubectl get crd inferenceservices.serving.kserve.io &>/dev/null; then
    err "InferenceService CRD not found after timeout."
    exit 1
fi
log "InferenceService CRD is ready."

# Step 2: Install controller resources
log "Installing KServe controller (deploymentMode=${DEPLOYMENT_MODE})..."
HELM_SETS=(
    --set "kserve.controller.deploymentMode=${DEPLOYMENT_MODE}"
)
if [[ "$ENABLE_INGRESS" == true ]]; then
    HELM_SETS+=(--set "kserve.controller.gateway.ingressGateway.enableIngress=true")
fi

helm install kserve "${OCI_REGISTRY}/kserve-resources" \
    --version "$KSERVE_VERSION" \
    --namespace "$KSERVE_NAMESPACE" \
    "${HELM_SETS[@]}" \
    --wait

# Step 3: Install ServingRuntimes (required for Standard mode)
log "Installing KServe ServingRuntimes (official v${KSERVE_VERSION} cluster resources)..."
kubectl apply --server-side -f "https://github.com/kserve/kserve/releases/download/${KSERVE_VERSION}/kserve-cluster-resources.yaml" 2>&1 || {
    warn "Some resources may not have been applied (LLMInferenceServiceConfig CRD may be missing). This is expected if LLM features are not needed."
}
log "ServingRuntimes installed."

# Step 4: Verify
log "Verifying installation..."
CONTROLLER_PODS=$(kubectl get pods -n "$KSERVE_NAMESPACE" -l control-plane=kserve-controller-manager --no-headers 2>/dev/null | wc -l)
if [[ "$CONTROLLER_PODS" -eq 0 ]]; then
    warn "No KServe controller pods found. Check with: kubectl get pods -n ${KSERVE_NAMESPACE}"
else
    log "KServe controller is running (${CONTROLLER_PODS} pod(s))."
fi

RUNTIME_COUNT=$(kubectl get clusterservingruntimes --no-headers 2>/dev/null | wc -l)
if [[ "$RUNTIME_COUNT" -gt 0 ]]; then
    log "ServingRuntimes installed (${RUNTIME_COUNT} runtimes)."
fi

echo ""
log "========================================="
log " KServe ${KSERVE_VERSION} installed successfully!"
log " Mode: ${DEPLOYMENT_MODE}"
log " Namespace: ${KSERVE_NAMESPACE}"
log "========================================="
echo ""
log "Verify installation:"
echo "  kubectl get pods -n ${KSERVE_NAMESPACE}"
echo "  kubectl get crd inferenceservices.serving.kserve.io"
echo ""
log "Uninstall:"
echo "  $0 --uninstall --namespace ${KSERVE_NAMESPACE}"
