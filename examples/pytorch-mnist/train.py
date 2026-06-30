"""
MNIST CNN 训练脚本

支持本地运行和 KubeAI 平台部署两种模式:

  本地:
      python train.py --epochs 10 --lr 0.001 --batch-size 128

  KubeAI 平台:
      通过环境变量自动读取配置 (MLFLOW_*, HP_*)

MLflow 日志:
  - 超参数 (learning_rate, epochs, batch_size, optimizer)
  - 每 epoch 指标 (train_loss, train_accuracy, val_loss, val_accuracy)
  - 最终测试集指标 (test_loss, test_accuracy, best_val_accuracy)
  - 训练曲线图
  - 混淆矩阵图
"""

import argparse
import json
import os
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
        "--output-dir",
        default="./output",
        help="模型输出目录 (KubeAI: KUBEAI_WORKSPACE_PATH)",
    )

    args = parser.parse_args()
    return {
        "learning_rate": args.lr,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "output_dir": args.output_dir,
        "device": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        "mlflow_tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        "mlflow_experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "mnist-cnn"),
        "mlflow_run_name": os.getenv("MLFLOW_RUN_NAME", None),
        "mlflow_run_id": os.getenv("MLFLOW_RUN_ID", None),
    }


# ============================================================================
# 数据加载
# ============================================================================


def load_data(batch_size: int) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """加载 MNIST 数据集并划分训练/验证/测试集。"""
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),  # MNIST 标准归一化
    ])

    full_train = MNIST(root="./data", train=True, download=True, transform=transform)
    test_dataset = MNIST(root="./data", train=False, download=True, transform=transform)

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

    print(f"数据加载完成: 训练 {train_size:,} | 验证 {val_size:,} | 测试 {len(test_dataset):,}")
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
    log_interval = max(1, num_batches // 5)
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

        if batch_idx % log_interval == 0 or batch_idx == num_batches:
            elapsed = time.time() - epoch_start
            eta = (elapsed / batch_idx) * (num_batches - batch_idx) if batch_idx > 0 else 0
            print(
                f"  [Epoch {epoch}/{total_epochs}] "
                f"Batch {batch_idx}/{num_batches} ({batch_idx / num_batches * 100:.0f}%) | "
                f"Loss: {total_loss / total:.4f} | Acc: {correct / total:.4f} | "
                f"ETA: {eta:.0f}s"
            )

    epoch_time = time.time() - epoch_start
    final_loss = total_loss / total
    final_acc = correct / total
    print(
        f"  [Epoch {epoch}/{total_epochs}] "
        f"完成 | Loss: {final_loss:.4f} | Acc: {final_acc:.4f} | "
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


def plot_confusion_matrix(labels: np.ndarray, preds: np.ndarray, class_names: list) -> plt.Figure:
    """绘制混淆矩阵。"""
    num_classes = len(class_names)
    cm = np.zeros((num_classes, num_classes), dtype=np.int64)
    for t, p in zip(labels, preds):
        cm[t, p] += 1

    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    fig.colorbar(im, ax=ax)

    ax.set(
        xticks=np.arange(num_classes),
        yticks=np.arange(num_classes),
        xticklabels=class_names,
        yticklabels=class_names,
        xlabel="预测标签",
        ylabel="真实标签",
        title="混淆矩阵",
    )
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    thresh = cm.max() / 2.0
    for i in range(num_classes):
        for j in range(num_classes):
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
    print("MNIST CNN 训练")
    print("=" * 60)
    print(f"  设备:         {config['device']}")
    print(f"  学习率:       {config['learning_rate']}")
    print(f"  Epochs:       {config['epochs']}")
    print(f"  Batch Size:   {config['batch_size']}")
    print(f"  输出目录:     {config['output_dir']}")

    os.makedirs(config["output_dir"], exist_ok=True)

    # 加载数据
    train_loader, val_loader, test_loader = load_data(config["batch_size"])

    # 类别标签
    labels_path = "class_labels.json"
    if os.path.exists(labels_path):
        with open(labels_path, "r", encoding="utf-8") as f:
            class_labels = json.load(f)
        class_names = [class_labels[str(i)] for i in range(10)]
    else:
        class_names = [str(i) for i in range(10)]

    # 初始化 MLflow
    mlflow.set_tracking_uri(config["mlflow_tracking_uri"])
    mlflow.set_experiment(config["mlflow_experiment_name"])
    print(f"\nMLflow 实验: {config['mlflow_experiment_name']}")
    if config["mlflow_run_id"]:
        print(f"  恢复平台预创建的 run: {config['mlflow_run_id']}")

    # 创建模型
    model = MNISTCNN(num_classes=10).to(config["device"])
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=config["learning_rate"])

    print(f"\n模型参数量: {sum(p.numel() for p in model.parameters()):,}")

    # 训练循环
    train_losses, train_accs = [], []
    val_losses, val_accs = [], []

    run_ctx = (
        mlflow.start_run(run_id=config["mlflow_run_id"]) if config["mlflow_run_id"]
        else mlflow.start_run(run_name=config["mlflow_run_name"])
    )

    with run_ctx:
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

            print(
                f"\n  Epoch {epoch}/{config['epochs']} 总结 | "
                f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f} | "
                f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f}\n"
            )

            mlflow.log_metrics(
                {
                    "train_loss": train_loss,
                    "train_accuracy": train_acc,
                    "val_loss": val_loss,
                    "val_accuracy": val_acc,
                },
                step=epoch,
            )

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                torch.save(model.state_dict(), os.path.join(config["output_dir"], "mnist_cnn_best.pt"))

        # 最终测试集评估
        test_loss, test_acc, all_preds, all_labels = evaluate(
            model, test_loader, criterion, config["device"]
        )
        print(f"\n测试集结果: Loss: {test_loss:.4f} | Accuracy: {test_acc:.4f}")

        torch.save(model.state_dict(), os.path.join(config["output_dir"], "mnist_cnn.pt"))
        print(f"模型已保存: {config['output_dir']}/mnist_cnn.pt")

        # MLflow: 最终指标 + 图表
        mlflow.log_metrics({
            "test_loss": test_loss,
            "test_accuracy": test_acc,
            "best_val_accuracy": best_val_acc,
        })

        metrics_fig = plot_metrics(train_losses, train_accs, val_losses, val_accs)
        mlflow.log_figure(metrics_fig, "training_curves.png")
        plt.close(metrics_fig)

        cm_fig = plot_confusion_matrix(all_labels, all_preds, class_names)
        mlflow.log_figure(cm_fig, "confusion_matrix.png")
        plt.close(cm_fig)

    print("\n训练完成！")
    print(f"  最佳验证准确率: {best_val_acc:.4f}")
    print(f"  测试准确率:     {test_acc:.4f}")


if __name__ == "__main__":
    main()
