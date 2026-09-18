# Build context: project root
# docker build -t kubeai-docs -f infra/images/docs/Dockerfile .

# Stage 1: Build
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --group docs

COPY mkdocs.yml .
COPY docs/ docs/

ENV NO_MKDOCS_2_WARNING=1
RUN uv run mkdocs build --config-file mkdocs.yml

# Stage 2: Runtime
# Pinned exact version: 离线内网部署, 不允许 entrypoint 行为随浮动 tag 漂移
FROM nginx:1.31.6-alpine

# 上游该脚本每次启动都执行 `apk manifest nginx` 校验 default.conf checksum,
# 会从 dl-cdn.alpinelinux.org 拉取 APKINDEX, 无公网时卡死在 entrypoint、nginx 无法启动。
RUN rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh

COPY --from=builder /app/site /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://127.0.0.1/"]

CMD ["nginx", "-g", "daemon off;"]
