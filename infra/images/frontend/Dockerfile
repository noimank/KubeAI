# Build context: project root
# docker build -t kubeai-frontend -f infra/images/frontend/Dockerfile .

# Stage 1: Build
FROM node:24-alpine AS builder

RUN corepack enable && corepack prepare pnpm@10 --activate

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ .
RUN pnpm build

# Stage 2: Runtime
# Pinned exact version: 离线内网部署, 不允许 entrypoint 行为随浮动 tag 漂移
FROM nginx:1.31.6-alpine

# 上游该脚本每次启动都执行 `apk manifest nginx` 校验 default.conf checksum,
# 会从 dl-cdn.alpinelinux.org 拉取 APKINDEX, 无公网时卡死在 entrypoint、nginx 无法启动。
# 我们在下方完全替换 default.conf, 该脚本(仅用于给镜像自带配置补 IPv6 listen)已无意义。
RUN rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://127.0.0.1/"]

CMD ["nginx", "-g", "daemon off;"]
