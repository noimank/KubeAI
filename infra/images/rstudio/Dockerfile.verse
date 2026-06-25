# RStudio + Tidyverse (CPU)
# R development with tidyverse, TeX, and common R packages
#
# Native entrypoint — runs directly on port 8888.
# The KubeAI backend runs "rserver" directly with --www-root-path
# set to the environment's path prefix (APISIX does NOT strip the prefix).
# Auth is disabled in rserver.conf; authentication is handled by the
# APISIX forward-auth layer.
#
# Build:
#   docker build -t kubeai-rstudio-verse -f Dockerfile.verse .
#   docker build -t hub.uimpcloud.com/kubeai/rstudio-env:base -f Dockerfile.verse .

# Pin the base image. Avoid `latest` because rocker may switch Ubuntu/R versions
# and default package repositories (for example p3m noble) without notice.
FROM rocker/verse:4.4.3

ENV CRAN_REPO=https://cloud.r-project.org

USER root

# 安装 uv（用于 Python/reticulate 环境下的包管理）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    gfortran \
    libcurl4-openssl-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev \
    libjpeg-dev \
    libpng-dev \
    libssl-dev \
    libtiff5-dev \
    libxml2-dev \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Optional R packages for the default CPU RStudio image.
RUN install2.r --error --skipinstalled -r "$CRAN_REPO" -n 4 \
    shiny \
    plumber \
    randomForest \
    xgboost \
    glmnet \
    plotly \
    reticulate

# RStudio Server runtime config — only session-default-working-dir is kept here;
# server-port and auth-none are passed as CLI args by the KubeAI backend.
# /kubeai and /workspace are hostPath volumes (permissions handled by initContainer).
RUN mkdir -p /etc/rstudio \
    && printf '%s\n' \
        'session-default-working-dir=/kubeai/home' \
        > /etc/rstudio/rsession.conf

USER rstudio

EXPOSE 8888
