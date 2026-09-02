# Runtime: PyTorch GPU
# Deep learning runtime with PyTorch + CUDA 12 support for GPU-accelerated training
#
# Build:
#   docker build -t hub.uimpcloud.com/kubeai/runtime:pytorch-gpu -f pytorch-gpu.Dockerfile .

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

# 安装 Python 3.12（从 deadsnakes PPA）
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 设置 python3.12 为默认 python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# 安装 uv（与 KubeAI 后端一致的 Python 包管理器）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# 基础 ML 依赖（所有运行时镜像共享）
RUN uv pip install --no-cache --system \
    numpy \
    pandas \
    scipy \
    matplotlib \
    scikit-learn \
    mlflow \
    fastapi \
    uvicorn \
    onnx \
    onnxruntime-gpu \
    tensorboard \
    tqdm \
    pyyaml \
    typing-extensions

# PyTorch GPU（CUDA 12.4）
RUN uv pip install --no-cache --system \
    torch \
    torchvision \
    torchaudio \
    --index-url https://download.pytorch.org/whl/cu124

# 常用深度学习生态包
RUN uv pip install --no-cache --system \
    transformers \
    datasets \
    accelerate \
    wandb \
    optuna \
    plotly \
    tensorboardx \
    neuralforecast

EXPOSE 8000

CMD ["python3"]
