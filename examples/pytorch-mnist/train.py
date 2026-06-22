"""
MNIST CNN 训练脚本

支持本地运行和 KubeAI 平台部署两种模式:

  本地:
      python train.py --epochs 10 --lr 0.001 --batch-size 128

  KubeAI 平台:
      通过环境变量自动读取配置 (KUBEAI_*, MLFLOW_*, HP_*)

MLflow 日志:
  - 超参数 (learning_rate, epochs, batch_size, optimizer)
  - 每 epoch 指标 (train_loss, train_acc, val_loss, val_acc)
  - 模型产物 (PyTorch 模型)
  - 混淆矩阵图
  - 模型文件输出到 ./output/mnist_cnn.pt
"""

import argparse
import json
import os
import sys
import time
from typing import Tuple

import matplotlib
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision.transforms as transforms
from torch.utils.data import DataLoader, random_split
from torchvision.datasets import MNIST

matplotlib.use("Agg")  # 非交互后端，适配无桌面环境
import matplotlib.pyplot as plt
import mlflow
import numpy as np


# ============================================================================
# 模型定义
# ============================================================================


class MNISTCNN(nn.Module):
    """简单的 CNN 模型，适配 MNIST 28x28 灰度图。

    Architecture:
        Conv2d(1, 32, 3) → ReLU → MaxPool2d(2)
        Conv2d(32, 64, 3) → ReLU → MaxPool2d(2)
        Flatten → FC(1600, 128) → ReLU → Dropout(0.5)
        FC(128, 10)
    """

    def __init__(self, num_classes: int = 10, dropout: float = 0.5):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)  # 28→14→7
        self.fc1 = nn.Linear(64 * 7 * 7, 128)
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(128, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x


# ============================================================================
# 配置解析
# ============================================================================


def get_config() -> dict:
    """从命令行参数 / 环境变量解析训练配置。

    环境变量优先级: 命令行 > 环境变量 > 默认值
    KubeAI 环境变量: HP_LEARNING_RATE, HP_EPOCHS, HP_BATCH_SIZE
    """
    # 从环境变量读取默认值（KubeAI 模式）
    env_defaults = {
        "learning_rate": float(os.getenv("HP_LEARNING_RATE", "0.001")),
        "epochs": int(os.getenv("HP_EPOCHS", "5")),
        "batch_size": int(os.getenv("HP_BATCH_SIZE", "64")),
    }

    parser = argparse.ArgumentParser(description="MNIST CNN 训练脚本")
    parser.add_argument(
        "--lr", "--learning-rate",
        type=float,
        default=env_defaults["learning_rate"],
        help=f"学习率 (默认: {env_defaults['learning_rate']})",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=env_defaults["epochs"],
        help=f"训练轮数 (默认: {env_defaults['epochs']})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=env_defaults["batch_size"],
        help=f"批次大小 (默认: {env_defaults['batch_size']})",
    )
    parser.add_argument(
        "--no-mlflow",
        action="store_true",
        help="禁用 MLflow 日志",
    )
    parser.add_argument(
        "--data-path",
        default=os.getenv("KUBEAI_DATASET_PATH", "./data"),
        help="数据集路径 (默认: ./data, KubeAI: KUBEAI_DATASET_PATH)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("KUBEAI_WORKSPACE_PATH", "./output"),
        help="模型输出目录 (默认: ./output, KubeAI: KUBEAI_WORKSPACE_PATH)",
    )

    args = parser.parse_args()
    return {
        "learning_rate": args.lr,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "no_mlflow": args.no_mlflow,
        "data_path": args.data_path,
        "output_dir": args.output_dir,
        "device": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        "mlflow_tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        "mlflow_experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "mnist-cnn"),
        "mlflow_run_name": os.getenv("MLFLOW_RUN_NAME", None),
    }


# ============================================================================
# 数据加载
# ============================================================================


def load_data(
    data_path: str, batch_size: int
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """加载 MNIST 数据集并划分训练/验证/测试集。"""
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),  # MNIST 标准归一化
    ])

    # 尝试从指定路径加载
    full_train = MNIST(root=data_path, train=True, download=True, transform=transform)
    test_dataset = MNIST(root=data_path, train=False, download=True, transform=transform)

    # 训练集 90% / 验证集 10%
    train_size = int(0.9 * len(full_train))
    val_size = len(full_train) - train_size
    train_dataset, val_dataset = random_split(
        full_train, [train_size, val_size],
        generator=torch.Generator().manual_seed(42),
    )

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    print(f"📊 数据加载完成: 训练 {train_size:,} | 验证 {val_size:,} | 测试 {len(test_dataset):,}")
    return train_loader, val_loader, test_loader


# ============================================================================
# 训练 & 评估
# ============================================================================


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
    epoch: int,
    total_epochs: int,
) -> Tuple[float, float]:
    """训练一个 epoch，返回 (平均 loss, 准确率)。"""
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    num_batches = len(loader)
    log_interval = max(1, num_batches // 5)  # 每 20% 打印一次进度
    epoch_start = time.time()

    for batch_idx, (data, target) in enumerate(loader, start=1):
        data, target = data.to(device), target.to(device)

        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * data.size(0)
        pred = output.argmax(dim=1)
        correct += pred.eq(target).sum().item()
        total += data.size(0)

        # 批次进度日志
        if batch_idx % log_interval == 0 or batch_idx == num_batches:
            current_loss = total_loss / total
            current_acc = correct / total
            progress = batch_idx / num_batches * 100
            elapsed = time.time() - epoch_start
            # 预估剩余时间
            eta = (elapsed / batch_idx) * (num_batches - batch_idx)
            print(
                f"    [Epoch {epoch}/{total_epochs}] "
                f"Batch {batch_idx}/{num_batches} ({progress:.0f}%) | "
                f"Loss: {current_loss:.4f} | Acc: {current_acc:.4f} | "
                f"Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s"
            )

    epoch_time = time.time() - epoch_start
    final_loss = total_loss / total
    final_acc = correct / total
    print(
        f"    [Epoch {epoch}/{total_epochs}] "
        f"✅ 完成 | Loss: {final_loss:.4f} | Acc: {final_acc:.4f} | "
        f"耗时: {epoch_time:.1f}s"
    )

    return final_loss, final_acc


@torch.no_grad()
def evaluate(
    model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device
) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """评估模型，返回 (平均 loss, 准确率, 所有预测, 所有标签)。"""
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds, all_labels = [], []

    for data, target in loader:
        data, target = data.to(device), target.to(device)
        output = model(data)
        loss = criterion(output, target)

        total_loss += loss.item() * data.size(0)
        pred = output.argmax(dim=1)
        correct += pred.eq(target).sum().item()
        total += data.size(0)

        all_preds.extend(pred.cpu().numpy())
        all_labels.extend(target.cpu().numpy())

    return total_loss / total, correct / total, np.array(all_preds), np.array(all_labels)


def _compute_confusion_matrix(labels: np.ndarray, preds: np.ndarray, num_classes: int) -> np.ndarray:
    """手动计算混淆矩阵（避免引入 sklearn 依赖）。"""
    cm = np.zeros((num_classes, num_classes), dtype=np.int64)
    for t, p in zip(labels, preds):
        cm[t, p] += 1
    return cm


def plot_confusion_matrix(labels: np.ndarray, preds: np.ndarray, class_names: list) -> plt.Figure:
    """绘制混淆矩阵。"""
    cm = _compute_confusion_matrix(labels, preds, len(class_names))
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    ax.figure.colorbar(im, ax=ax)

    ax.set(
        xticks=np.arange(cm.shape[1]),
        yticks=np.arange(cm.shape[0]),
        xticklabels=class_names,
        yticklabels=class_names,
        xlabel="预测标签",
        ylabel="真实标签",
        title="混淆矩阵",
    )
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # 在格子里标注数值
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j, i, str(cm[i, j]),
                ha="center", va="center",
                color="white" if cm[i, j] > thresh else "black",
            )

    fig.tight_layout()
    return fig


def plot_metrics(
    train_losses: list, train_accs: list, val_losses: list, val_accs: list
) -> plt.Figure:
    """绘制训练曲线。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    epochs = range(1, len(train_losses) + 1)
    ax1.plot(epochs, train_losses, "b-", label="训练 Loss")
    ax1.plot(epochs, val_losses, "r-", label="验证 Loss")
    ax1.set(xlabel="Epoch", ylabel="Loss", title="Loss 曲线")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(epochs, train_accs, "b-", label="训练 准确率")
    ax2.plot(epochs, val_accs, "r-", label="验证 准确率")
    ax2.set(xlabel="Epoch", ylabel="Accuracy", title="准确率曲线")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


# ============================================================================
# 主流程
# ============================================================================


def main() -> None:
    config = get_config()

    print("=" * 60)
    print("🚀 MNIST CNN 训练")
    print("=" * 60)
    print(f"  设备:         {config['device']}")
    print(f"  学习率:       {config['learning_rate']}")
    print(f"  Epochs:       {config['epochs']}")
    print(f"  Batch Size:   {config['batch_size']}")
    print(f"  数据路径:     {config['data_path']}")
    print(f"  输出目录:     {config['output_dir']}")
    print(f"  MLflow:       {'禁用' if config['no_mlflow'] else config['mlflow_tracking_uri']}")

    # 准备输出目录
    os.makedirs(config["output_dir"], exist_ok=True)

    # 加载数据
    train_loader, val_loader, test_loader = load_data(
        config["data_path"], config["batch_size"]
    )

    # 加载类别标签
    labels_path = os.path.join(config["data_path"], "class_labels.json")
    if os.path.exists(labels_path):
        with open(labels_path, "r", encoding="utf-8") as f:
            class_labels = json.load(f)
        class_names = [class_labels[str(i)] for i in range(10)]
    else:
        class_names = [str(i) for i in range(10)]

    # 初始化 MLflow
    if not config["no_mlflow"]:
        mlflow.set_tracking_uri(config["mlflow_tracking_uri"])
        mlflow.set_experiment(config["mlflow_experiment_name"])
        print(f"\n📈 MLflow 实验: {config['mlflow_experiment_name']}")

    # 创建模型
    model = MNISTCNN(num_classes=10).to(config["device"])
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=config["learning_rate"])

    print(f"\n📐 模型参数量: {sum(p.numel() for p in model.parameters()):,}")

    # 训练循环
    train_losses, train_accs = [], []
    val_losses, val_accs = [], []

    with mlflow.start_run(run_name=config["mlflow_run_name"]) if not config["no_mlflow"] else _dummy_context():
        # 日志超参
        if not config["no_mlflow"]:
            mlflow.log_params({
                "learning_rate": config["learning_rate"],
                "epochs": config["epochs"],
                "batch_size": config["batch_size"],
                "optimizer": "Adam",
                "model": "MNISTCNN",
                "device": str(config["device"]),
            })

        best_val_acc = 0.0
        for epoch in range(1, config["epochs"] + 1):
            epoch_start = time.time()

            train_loss, train_acc = train_epoch(
                model, train_loader, optimizer, criterion, config["device"],
                epoch, config["epochs"],
            )
            val_loss, val_acc, _, _ = evaluate(
                model, val_loader, criterion, config["device"]
            )

            train_losses.append(train_loss)
            train_accs.append(train_acc)
            val_losses.append(val_loss)
            val_accs.append(val_acc)

            # 当前学习率（固定 lr 时不变，但方便后续引入 scheduler）
            current_lr = optimizer.param_groups[0]["lr"]

            print(
                f"\n  📊 Epoch {epoch}/{config['epochs']} 总结 | "
                f"LR: {current_lr:.6f} | "
                f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f} | "
                f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f} | "
                f"总耗时: {time.time() - epoch_start:.1f}s\n"
            )

            # MLflow 日志每轮指标
            if not config["no_mlflow"]:
                mlflow.log_metrics(
                    {
                        "train_loss": train_loss,
                        "train_accuracy": train_acc,
                        "val_loss": val_loss,
                        "val_accuracy": val_acc,
                    },
                    step=epoch,
                )

            # 保存最佳模型
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_model_path = os.path.join(config["output_dir"], "mnist_cnn_best.pt")
                torch.save(model.state_dict(), best_model_path)

        # 最终测试集评估
        test_loss, test_acc, all_preds, all_labels = evaluate(
            model, test_loader, criterion, config["device"]
        )
        print(f"\n📊 测试集结果: Loss: {test_loss:.4f} | Accuracy: {test_acc:.4f}")

        # 保存最终模型
        final_model_path = os.path.join(config["output_dir"], "mnist_cnn.pt")
        torch.save(model.state_dict(), final_model_path)
        print(f"💾 模型已保存: {final_model_path}")

        # MLflow 日志最终指标 & 图表 & 模型
        if not config["no_mlflow"]:
            mlflow.log_metrics({
                "test_loss": test_loss,
                "test_accuracy": test_acc,
                "best_val_accuracy": best_val_acc,
            })

            # 训练曲线
            metrics_fig = plot_metrics(train_losses, train_accs, val_losses, val_accs)
            mlflow.log_figure(metrics_fig, "training_curves.png")
            plt.close(metrics_fig)

            # 混淆矩阵
            cm_fig = plot_confusion_matrix(all_labels, all_preds, class_names)
            mlflow.log_figure(cm_fig, "confusion_matrix.png")
            plt.close(cm_fig)

            # 模型产物
            mlflow.pytorch.log_model(model, "model", registered_model_name="mnist-cnn")

    print("\n✅ 训练完成！")
    print(f"   最佳验证准确率: {best_val_acc:.4f}")
    print(f"   测试准确率:     {test_acc:.4f}")


class _dummy_context:
    """空上下文管理器，用于 MLflow 禁用时的占位。"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


if __name__ == "__main__":
    main()
