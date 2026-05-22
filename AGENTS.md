# Repository Guidelines

## Project Structure

KubeAI is split into a FastAPI backend, a React/Vite frontend, and Kubernetes deployment assets.

- `backend/app/`: API entrypoint, routers, config/security, SQLAlchemy models, Pydantic schemas, services, middleware, and K8s integrations.
- `backend/tests/`: pytest tests; async tests use `pytest-asyncio` with `asyncio_mode=auto`.
- `frontend/src/`: React app, routes in `App.tsx`, API client, Zustand stores, guards, and components.
- `frontend/tests/`: Vitest setup and frontend tests.
- `infra/`: Helm chart, image Dockerfiles, and infrastructure scripts.
- `docs/`, `data/`: documentation and local data artifacts.

## Commands

Run backend commands from `backend/`:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy app/
```

Run frontend commands from `frontend/`:

```bash
pnpm install
pnpm dev
pnpm build
pnpm lint
pnpm typecheck
pnpm test
```

Deploy dev Helm resources from the repository root:

```bash
helm install kubeai infra/helm/kubeai/ -f infra/helm/kubeai/values-dev.yaml -n kubeai --create-namespace
```

## Coding Style

Backend code targets Python 3.12, uses Ruff with 120-character lines and double quotes, and runs strict mypy. Keep API responses wrapped in `BaseResponse[T]`.

Frontend code uses TypeScript, React, Ant Design, Zustand, ESLint 9, and Prettier with 2-space indentation, single quotes, no semicolons, and 100-character print width. The Vite alias `@` maps to `frontend/src/`. User-visible UI text must be zh-CN.

## Testing Guidelines

Name backend tests `test_*.py` under `backend/tests/`; run one test with:

```bash
uv run pytest tests/unit/test_security.py::test_hash_password -v
```

Frontend tests use Vitest and jsdom. Run `pnpm test` before submitting UI changes. Add or update tests when changing shared services, auth, permissions, API transforms, or user-facing workflows.

## Commit & Pull Request Guidelines

Recent history uses emoji-prefixed Conventional Commits, for example `✨ feat: ...`, `🔒 fix: ...`, `♻️ refactor: ...`, `✅ test: ...`, and `🔧 chore: ...`. Keep commits scoped and use Chinese summaries when matching history.

Pull requests should include a short description, linked issue or task, verification commands, screenshots for UI changes, and notes for migrations or Helm/config changes.

## Security & Configuration Tips

Backend `.env` files may contain real credentials. Do not commit secrets; keep examples sanitized. Endpoint modules must be mounted in `backend/app/api/endpoints/router.py` before use. Tailwind preflight is disabled for Ant Design, and dark mode uses `[data-theme="dark"]`.
