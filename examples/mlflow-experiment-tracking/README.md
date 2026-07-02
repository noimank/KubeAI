# KubeAI 实验追踪与可视化示例

本示例演示如何在 KubeAI 平台上使用 **MLflow + TensorBoard** 双通道进行实验追踪与可视化，无需真实 GPU 或大规模数据集，通过模拟训练过程生成丰富的指标和图表。

## 功能亮点

- **双通道实验追踪** — **MLflow** + **TensorBoard** 同时记录，互不依赖，可独立启用
- **MLflow 特性** — 超参数、epoch/step 级指标、可视化图表 artifact、训练摘要 JSON
- **TensorBoard 特性** — 标量曲线、权重/梯度直方图、PR 曲线、HParams 超参面板、可视化图像
- **多维度指标** — loss、accuracy、precision、recall、f1-macro、gradient_norm、learning_rate 等
- **多粒度日志** — epoch 级汇总 + step 级细粒度（每 epoch ~10 个采样点）
- **丰富可视化** — 训练曲线、混淆矩阵、ROC 曲线、各类别 F1 变化、Loss Gap（过拟合指标）
- **Artifact 产物** — 图表、混淆矩阵 JSON、训练摘要 JSON
- **多实验对比** — 批量运行不同超参数组合，自动生成对比图表

---

## 快速开始

### 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- MLflow Tracking Server（本地或 KubeAI 平台提供）

### 安装依赖

```bash
cd examples/mlflow-experiment-tracking
uv sync
```

### 启动 MLflow UI（本地）

```bash
uv run mlflow ui --port 5000
```

### 启动 TensorBoard（本地）

```bash
uv run tensorboard --logdir=./output/tensorboard_logs --port 6006
```

---

## 脚本说明

### 1. 单实验训练 — `train.py`

运行单个模拟训练任务，记录完整的训练指标和可视化图表。

```bash
# 默认参数（20 epochs）— MLflow + TensorBoard 同时启用
uv run python train.py

# 自定义超参数
uv run python train.py --epochs 50 --lr 0.005 --hidden-dim 512 --dropout 0.2

# 仅启用 TensorBoard（禁用 MLflow）
uv run python train.py --no-mlflow

# 仅启用 MLflow（禁用 TensorBoard）
uv run python train.py --no-tensorboard

# 全部禁用（纯控制台输出）
uv run python train.py --no-mlflow --no-tensorboard

# 自定义随机种子
uv run python train.py --seed 123
```

**MLflow 记录内容：**

| 类型 | 内容 |
|------|------|
| 参数 | learning_rate, epochs, batch_size, hidden_dim, num_layers, dropout, warmup_epochs, seed, optimizer, scheduler, model_architecture |
| 指标 (epoch) | train_loss, train_accuracy, val_loss, val_accuracy, val_precision, val_recall, val_f1_macro, learning_rate, epoch_time_seconds |
| 指标 (step) | step_loss, step_accuracy, step_gradient_norm |
| 最终指标 | test_loss, test_accuracy, test_f1_macro, best_val_accuracy |
| Artifact | training_curves.png, confusion_matrix.png, roc_curves.png, per_class_f1.png, confusion_matrix.json, training_summary.json |

**TensorBoard 记录内容：**

| 类型 | 内容 |
|------|------|
| 标量 (Scalars) | Loss/train, Loss/val, Accuracy/train, Accuracy/val, Metrics/*, Training/* |
| 直方图 (Histograms) | weights/layer{0-4}, gradients/layer{0-4}（每 epoch） |
| PR 曲线 | pr_curve/class{0-9}（每 5 个 epoch） |
| HParams | 超参面板（lr, epochs, batch_size, hidden_dim, num_layers, dropout） |
| 图像 (Images) | visualization/*（训练曲线、混淆矩阵、ROC、各类别 F1） |

### 2. 多实验对比 — `compare_experiments.py`

批量运行 5 组不同超参数的实验，自动生成对比图表。

```bash
uv run python compare_experiments.py
```

预定义实验组：

| 实验名 | 说明 |
|--------|------|
| `baseline` | 基准配置 |
| `high_lr` | 高学习率 (0.01) |
| `large_model` | 更大模型 (512x5) |
| `low_dropout` | 低 dropout (0.1) |
| `small_batch` | 小 batch size (32) |

**输出对比图表：**
- `comparison_loss_acc.png` — 各实验 loss / accuracy 曲线对比
- `comparison_final_metrics.png` — 最终指标柱状图对比

---

## KubeAI 平台部署

### 构建镜像

```bash
cd examples/mlflow-experiment-tracking
docker build -t harbor.kubeai.local/kubeai/mlflow-tracking-demo:latest .
docker push harbor.kubeai.local/kubeai/mlflow-tracking-demo:latest
```

### 创建训练任务

在 KubeAI 控制台：

1. **镜像管理** → 添加自定义镜像 `mlflow-tracking-demo:latest`
2. **创建训练任务** → 选择该镜像
3. **Command**: `python train.py --epochs 30 --hidden-dim 512`
4. **超参数**（可选）：
   - `learning_rate=0.001`
   - `epochs=30`
   - `batch_size=128`
   - `hidden_dim=512`
5. 启动任务，KubeAI 会自动：
   - 注入 `MLFLOW_TRACKING_URI`、`MLFLOW_EXPERIMENT_NAME`、`MLFLOW_RUN_ID`
   - 任务完成后在「实验」页面查看 MLflow 追踪结果

### 多实验对比任务

```bash
# Command
python compare_experiments.py
```

对比结果会记录到 `simulate-training-comparison` 实验下，可在 MLflow UI 中横向对比各 run。

### TensorBoard 可视化

KubeAI 平台在创建训练任务时，如果勾选了「启用 TensorBoard」：
1. 平台自动注入 `TENSORBOARD_LOG_DIR` 环境变量
2. 在训练 pod 中以 sidecar 形式启动 TensorBoard 服务
3. 训练过程中产生的日志自动被读取
4. 在 KubeAI 控制台 → 训练任务 → TensorBoard 标签页中直接查看

本地查看 TensorBoard 日志：
```bash
uv run tensorboard --logdir=./output/tensorboard_logs --port 6006
```

---

## 环境变量

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `MLFLOW_TRACKING_URI` | MLflow Tracking 服务地址 | `http://localhost:5000` |
| `MLFLOW_EXPERIMENT_NAME` | 实验名称 | `simulate-training` |
| `MLFLOW_RUN_NAME` | Run 名称 | 自动生成 |
| `MLFLOW_RUN_ID` | 预创建 Run ID（KubeAI 注入） | 无 |
| `TENSORBOARD_LOG_DIR` | TensorBoard 日志输出目录 | `./output/tensorboard_logs` |
| `HP_LEARNING_RATE` | 学习率 | `0.001` |
| `HP_EPOCHS` | 训练轮数 | `20` |
| `HP_BATCH_SIZE` | 批次大小 | `128` |
| `HP_HIDDEN_DIM` | 隐藏层维度 | `256` |
| `HP_NUM_LAYERS` | 网络层数 | `3` |
| `HP_DROPOUT` | Dropout 比例 | `0.3` |
| `HP_WARMUP_EPOCHS` | Warmup 轮数 | `3` |
| `HP_SEED` | 随机种子 | `42` |
| `KUBEAI_WORKSPACE_PATH` | 工作空间输出目录 | `./output` |

---

## 项目结构

```
mlflow-experiment-tracking/
├── README.md                  # 本文档
├── pyproject.toml             # uv 项目配置
├── .gitignore                 # Git 忽略规则
├── train.py                   # 单实验模拟训练
├── compare_experiments.py     # 多实验对比
├── Dockerfile                 # KubeAI 部署镜像
├── output/                    # 图表/日志输出（自动生成）
└── mlruns/                    # MLflow 本地日志（自动生成）
```

---

## 查看结果

### 本地 MLflow UI

```bash
uv run mlflow ui --port 5000
```

打开 http://localhost:5000 查看：
- **Experiments** → 查看各实验列表
- **Runs** → 查看单次训练详情
- **Metrics** → 查看指标曲线（支持多 run 对比）
- **Parameters** → 查看超参数
- **Artifacts** → 查看图表和 JSON 文件

### 本地 TensorBoard

```bash
uv run tensorboard --logdir=./output/tensorboard_logs --port 6006
```

打开 http://localhost:6006 查看：
- **Scalars** → Loss / Accuracy / Metrics / Training 各面板标量曲线
- **Histograms** → 各层权重和梯度分布随 epoch 变化
- **PR Curves** → 各类别 Precision-Recall 曲线
- **HParams** → 超参数对比面板
- **Images** → 训练曲线、混淆矩阵、ROC 等可视化图像

### KubeAI 平台

在 KubeAI 控制台 → 训练任务：
- **关联实验** → 点击「查看 MLflow」跳转
- **TensorBoard** → 点击「打开 TensorBoard」跳转（任务需启用 TensorBoard）
