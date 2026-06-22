# Runtime: TensorFlow CPU
# TensorFlow CPU runtime for deep learning training and inference
#
# Build:
#   docker build -t hub.uimpcloud.com/kubeai/runtime:tensorflow-cpu -f tensorflow-cpu.Dockerfile .

FROM python:3.12-slim-bookworm

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

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
    onnxruntime \
    tensorboard \
    tqdm \
    pyyaml \
    typing-extensions

# TensorFlow CPU
RUN uv pip install --no-cache --system \
    tensorflow \
    tf-keras

# 常用深度学习生态包
RUN uv pip install --no-cache --system \
    transformers \
    datasets \
    wandb \
    optuna \
    plotly \
    tensorflow-datasets

EXPOSE 8000

CMD ["python3"]
