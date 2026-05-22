# RStudio + ML (GPU)
# R machine learning with CUDA 12 GPU support
#
# KubeAI runs RStudio through JupyterHub:
#   jupyterhub-singleuser is the required main process.
#   jupyter-server-proxy is required to proxy sub-applications.
#   jupyter-rsession-proxy is required to expose RStudio at /rstudio/.
#
# Build:
#   docker build -t kubeai-rstudio-ml -f Dockerfile.ml .

FROM rocker/ml:4.4.3-cuda12.4

ENV CRAN_REPO=https://cloud.r-project.org

USER root

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

# KubeAI platform-required dependencies:
#   jupyterhub: provides jupyterhub-singleuser for Hub-managed pods.
#   jupyter-server-proxy: integrates proxied apps with Jupyter Server auth/routing.
#   jupyter-rsession-proxy: registers /rstudio/ and launches RStudio Server.
RUN pip3 install --no-cache-dir --break-system-packages \
    jupyterhub \
    jupyter-server-proxy \
    jupyter-rsession-proxy

# Optional R packages for the default GPU RStudio image.
# Explicit CRAN avoids failures when the base image's default binary repository
# is temporarily unavailable or not published for the current Ubuntu release.
RUN install2.r --error --skipinstalled -r "$CRAN_REPO" -n 4 \
    shiny \
    plumber \
    xgboost \
    glmnet \
    plotly \
    torch \
    tensorflow \
    reticulate

RUN mkdir -p /kubeai /workspace /etc/rstudio \
    && printf '%s\n' 'session-default-working-dir=/kubeai' > /etc/rstudio/rsession.conf \
    && chown rstudio:rstudio /kubeai /workspace

# Required: KubeSpawner runs jupyterhub-singleuser on 8888; RStudio is proxied behind it.
USER rstudio

EXPOSE 8888
