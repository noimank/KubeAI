# PyTorch MNIST 全流程示例

本示例演示使用 PyTorch 训练手写数字识别（MNIST）模型的全流程：

1. **数据准备** — 下载 MNIST 数据集
2. **模型训练** — 训练 CNN + MLflow 实验追踪
3. **模型导出** — 导出 TorchScript / ONNX 格式
4. **推理服务** — 本地 Flask HTTP 推理服务
5. **推理调用** — 客户端测试脚本

KubeAI 平台部署时，训练任务通过 Volcano VCJob 调度，MLflow 自动记录实验，模型注册后通过 KServe 部署推理服务。

---

## 快速开始（本地）

### 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器，与 KubeAI 后端保持一致）

### 1. 安装依赖

```bash
cd examples/pytorch-mnist
uv sync
```

### 2. 下载数据集

```bash
uv run python download_data.py
```

输出：
```
📥 下载 MNIST 数据集
[1/2] 下载训练集 (60,000 张)...
[2/2] 下载测试集 (10,000 张)...
✅ MNIST 数据集下载完成！
```

数据集将保存在 `./data/` 目录下。

### 3. 训练模型

```bash
# 默认参数训练
uv run python train.py

# 自定义参数
uv run python train.py --epochs 10 --lr 0.001 --batch-size 128

# CPU 训练（无 GPU 时自动使用）
uv run python train.py --epochs 5

# 禁用 MLflow（无 MLflow 服务时）
uv run python train.py --no-mlflow
```

训练完成后：
- 模型文件: `./output/mnist_cnn.pt`（最终模型）、`./output/mnist_cnn_best.pt`（最佳验证模型）
- MLflow 实验记录（如启用）

### 4. 查看 MLflow 实验

```bash
# 启动 MLflow UI
uv run mlflow ui --port 5000
```

打开 http://localhost:5000 查看：
- 超参数（learning_rate, epochs, batch_size）
- 每轮指标曲线（train/val loss, accuracy）
- 混淆矩阵
- 模型产物

### 5. 导出模型

```bash
# 导出所有格式
uv run python export_model.py

# 仅导出 TorchScript
uv run python export_model.py --format torchscript

# 仅导出 ONNX
uv run python export_model.py --format onnx
```

产物：
- `./output/mnist_cnn_traced.pt` — TorchScript 格式
- `./output/mnist_cnn.onnx` — ONNX 格式

### 6. 启动推理服务

```bash
uv run python serve.py --port 8080
```

输出：
```
🔮 MNIST CNN 推理服务
  模型:     ./output/mnist_cnn.pt
  设备:     cpu
  类别:     ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
🚀 服务启动: http://0.0.0.0:8080
```

API 端点：
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| POST | `/predict` | 推理（JSON body） |

### 7. 测试推理

```bash
# 随机测试集样本
uv run python client.py --count 5

# 指定本地图片
uv run python client.py --image my_digit.png
```

---

## KubeAI 平台使用指南

### 构建 Docker 镜像

```bash
cd examples/pytorch-mnist
docker build -t harbor.kubeai.local/kubeai/mnist-train:latest .
docker push harbor.kubeai.local/kubeai/mnist-train:latest
```

### 在 KubeAI 中创建训练任务

1. **注册镜像**: 在 KubeAI 控制台 → 镜像管理 → 添加自定义镜像
2. **上传数据集**: 数据集管理 → 上传 MNIST 数据集（或使用下载好的 `./data/` 目录内容）
3. **创建训练任务**:
   - 选择镜像: `mnist-train:latest`
   - Command: `python train.py --epochs 10 --batch-size 128`
   - GPU: 1 卡（或 CPU 亦可）
   - 超参数: `learning_rate=0.001`, `epochs=10`, `batch_size=128`
4. **查看实验**: 训练任务 → 关联实验 → MLflow UI

### 部署推理服务

1. **注册模型**: 训练完成后 → 工作空间产物 → 注册模型版本
2. **创建推理服务**: 选择模型版本 → 配置资源 → 部署
3. **调用推理**: 通过 KubeAI 推理代理端点调用

---

## 项目结构

```
pytorch-mnist/
├── README.md              # 本文档
├── pyproject.toml         # uv 项目配置 + 依赖
├── .gitignore             # Git 忽略规则
├── download_data.py       # 数据集下载
├── train.py               # 训练脚本（MLflow 日志）
├── export_model.py        # 模型导出（TorchScript/ONNX）
├── serve.py               # 推理 HTTP 服务
├── client.py              # 推理客户端
├── Dockerfile             # KubeAI 部署镜像
├── data/                  # 数据集（自动下载）
├── output/                # 模型产物
└── mlruns/                # MLflow 本地日志
```

---

## 各脚本环境变量参考

训练脚本 `train.py` 支持以下环境变量（KubeAI 平台自动注入）：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `MLFLOW_TRACKING_URI` | MLflow 服务地址 | `http://localhost:5000` |
| `MLFLOW_EXPERIMENT_NAME` | 实验名称 | `mnist-cnn` |
| `MLFLOW_RUN_NAME` | Run 名称 | 自动生成 |
| `HP_LEARNING_RATE` | 学习率 | `0.001` |
| `HP_EPOCHS` | 训练轮数 | `5` |
| `HP_BATCH_SIZE` | 批次大小 | `64` |
| `KUBEAI_DATASET_PATH` | 数据集挂载路径 | `./data` |
| `KUBEAI_WORKSPACE_PATH` | 工作空间路径 | `./output` |

模型架构：
```
Conv2d(1,32,3) → ReLU → MaxPool(2)
Conv2d(32,64,3) → ReLU → MaxPool(2)
Flatten → FC(1600,128) → ReLU → Dropout(0.5)
FC(128,10)
```

参数量：~110K
