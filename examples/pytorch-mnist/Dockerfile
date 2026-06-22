# KubeAI 训练镜像 — PyTorch MNIST 示例
#
# 本地构建与运行:
#   docker build -t pytorch-mnist:latest .
#   docker run --rm pytorch-mnist:latest train.py --epochs 2 --no-mlflow
#
# KubeAI 平台:
#   构建后推送至 Harbor，注册为 KubeAI 自定义镜像，
#   训练任务 command 填写 "python train.py --epochs 10"
#
# 与 KubeAI 后端镜像采用一致的 uv 包管理方式。

FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

# 安装 uv（与 KubeAI 后端 Dockerfile 一致）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1

# 安装 Python 依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 复制脚本
COPY download_data.py train.py serve.py export_model.py ./

# 创建输出目录
RUN mkdir -p /workspace/output /workspace/data

# 将 venv 加入 PATH
ENV PATH="/workspace/.venv/bin:$PATH"

# 默认命令: 训练（KubeAI 可通过 VCJob command 覆盖）
CMD ["python", "train.py"]
