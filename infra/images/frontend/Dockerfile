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
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:80/"]

CMD ["nginx", "-g", "daemon off;"]
