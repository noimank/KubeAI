# Runtime: Scikit-learn
# Lightweight CPU runtime for classical ML with scikit-learn ecosystem
#
# Build:
#   docker build -t hub.uimpcloud.com/kubeai/runtime:scikit -f scikit.Dockerfile .

FROM python:3.12-slim-bookworm

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    build-essential \
    libgomp1 \
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

# 经典 ML 扩展包
RUN uv pip install --no-cache --system \
    xgboost \
    lightgbm \
    optuna \
    plotly \
    seaborn \
    neuralforecast \
    imbalanced-learn \
    feature-engine \
    category-encoders \
    joblib \
    tensorboardx

EXPOSE 8000

CMD ["python3"]
