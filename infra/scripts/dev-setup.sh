#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[KubeAI]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# -- Check prerequisites
check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        warn "$1 not found. Please install it first."
        return 1
    fi
    return 0
}

log "Checking prerequisites..."
MISSING=0
for cmd in docker uv pnpm; do
    if ! check_cmd "$cmd"; then MISSING=1; fi
done
if [ $MISSING -eq 1 ]; then
    echo "Install missing tools and re-run this script."
    exit 1
fi

# -- Start infrastructure services
log "Starting PostgreSQL, Redis, MinIO..."
cd "$PROJECT_ROOT"
docker compose -f docker-compose.dev.yml up -d

# -- Wait for services
log "Waiting for services to be healthy..."
for i in $(seq 1 30); do
    if docker exec kubeai-postgres pg_isready &>/dev/null; then
        break
    fi
    sleep 1
done
log "PostgreSQL is ready."

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
log "Note: Training jobs require Volcano in a K8s cluster."
echo "  Install with: helm install volcano volcano-sh/volcano -n volcano-system --create-namespace"
