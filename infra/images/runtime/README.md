# Runtime Images

KubeAI 运行时镜像，为训练作业和推理服务提供开箱即用的 Python 3.12 环境。

## 镜像列表

| 镜像 | Dockerfile | 基础镜像 | 核心框架 | 适用场景 |
|------|-----------|---------|---------|---------|
| pytorch-gpu | `pytorch-gpu.Dockerfile` | `nvidia/cuda:12.4` | PyTorch + CUDA 12 | GPU 深度学习训练 |
| pytorch-cpu | `pytorch-cpu.Dockerfile` | `python:3.12-slim` | PyTorch (CPU) | CPU 推理、轻量训练 |
| scikit | `scikit.Dockerfile` | `python:3.12-slim` | scikit-learn, XGBoost, LightGBM | 经典 ML、表格数据 |
| tensorflow-cpu | `tensorflow-cpu.Dockerfile` | `python:3.12-slim` | TensorFlow (CPU) | CPU 深度学习 |

## 公共依赖

所有镜像预装：`mlflow`、`fastapi`、`onnx`、`numpy`、`pandas`、`scipy`、`scikit-learn`、`neuralforecast`、`tensorboard`、`matplotlib`、`tqdm`。

## 构建

```bash
docker build -t hub.uimpcloud.com/kubeai/runtime:pytorch-gpu -f pytorch-gpu.Dockerfile .
docker build -t hub.uimpcloud.com/kubeai/runtime:pytorch-cpu -f pytorch-cpu.Dockerfile .
docker build -t hub.uimpcloud.com/kubeai/runtime:scikit -f scikit.Dockerfile .
docker build -t hub.uimpcloud.com/kubeai/runtime:tensorflow-cpu -f tensorflow-cpu.Dockerfile .
```
