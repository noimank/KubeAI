"""
模拟训练脚本 — 展示 KubeAI 平台 MLflow + TensorBoard 实验追踪

无需真实 GPU，通过数学模型生成逼真的训练曲线。

本地:
    uv run python train.py

KubeAI 平台:
    环境变量自动注入: MLFLOW_*, TENSORBOARD_LOG_DIR, HP_*
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import matplotlib
import mlflow
import numpy as np
from matplotlib import pyplot as plt
from torch.utils.tensorboard import SummaryWriter

matplotlib.use("Agg")


# ============================================================================
# 配置
# ============================================================================


def get_config() -> dict[str, Any]:
    env_defaults = {
        "learning_rate": float(os.getenv("HP_LEARNING_RATE", "0.001")),
        "epochs": int(os.getenv("HP_EPOCHS", "20")),
        "batch_size": int(os.getenv("HP_BATCH_SIZE", "128")),
        "hidden_dim": int(os.getenv("HP_HIDDEN_DIM", "256")),
        "num_layers": int(os.getenv("HP_NUM_LAYERS", "3")),
        "dropout": float(os.getenv("HP_DROPOUT", "0.3")),
        "warmup_epochs": int(os.getenv("HP_WARMUP_EPOCHS", "3")),
        "seed": int(os.getenv("HP_SEED", "42")),
    }

    parser = argparse.ArgumentParser(description="KubeAI 实验追踪示例")
    parser.add_argument("--lr", type=float, default=env_defaults["learning_rate"])
    parser.add_argument("--epochs", type=int, default=env_defaults["epochs"])
    parser.add_argument("--batch-size", type=int, default=env_defaults["batch_size"])
    parser.add_argument("--hidden-dim", type=int, default=env_defaults["hidden_dim"])
    parser.add_argument("--num-layers", type=int, default=env_defaults["num_layers"])
    parser.add_argument("--dropout", type=float, default=env_defaults["dropout"])
    parser.add_argument("--warmup-epochs", type=int, default=env_defaults["warmup_epochs"])
    parser.add_argument("--seed", type=int, default=env_defaults["seed"])
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument("--no-tensorboard", action="store_true")

    args = parser.parse_args()
    return {
        "learning_rate": args.lr,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "hidden_dim": args.hidden_dim,
        "num_layers": args.num_layers,
        "dropout": args.dropout,
        "warmup_epochs": args.warmup_epochs,
        "seed": args.seed,
        "output_dir": args.output_dir,
        "use_mlflow": not args.no_mlflow,
        "use_tensorboard": not args.no_tensorboard,
        "tensorboard_log_dir": os.getenv("TENSORBOARD_LOG_DIR", "./output/tensorboard_logs"),
        "mlflow_tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        "mlflow_experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "simulate-training"),
        "mlflow_run_name": os.getenv("MLFLOW_RUN_NAME", None),
        "mlflow_run_id": os.getenv("MLFLOW_RUN_ID", None),
    }


# ============================================================================
# 模拟训练引擎
# ============================================================================


class MockTrainer:
    """用数学模型生成逼真训练曲线。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self.cfg = config
        self.rng = np.random.default_rng(config["seed"])
        self.num_train_samples = 50_000
        self.steps_per_epoch = self.num_train_samples // config["batch_size"]
        self.epoch = 0
        self.global_step = 0
        self.overfit = 0.0

    def _lr(self) -> float:
        lr = self.cfg["learning_rate"]
        e, total, w = self.epoch, self.cfg["epochs"], self.cfg["warmup_epochs"]
        if e < w:
            return lr * (e / w)
        p = (e - w) / max(1, total - w)
        return lr * 0.5 * (1 + np.cos(np.pi * p))

    def _step_metrics(self) -> dict[str, float]:
        base_loss = 2.5 * np.exp(-0.08 * self.epoch) + 0.15
        loss = max(0.05, base_loss + self.rng.normal(0, 0.05) + self.overfit * 0.02)
        base_acc = 1 - np.exp(-0.1 * self.epoch - 0.5)
        accuracy = min(0.999, max(0.1, base_acc + self.rng.normal(0, 0.01)))
        grad_norm = max(0.1, 2.0 * np.exp(-0.05 * self.epoch) + self.rng.normal(0, 0.1))
        self.global_step += 1
        return {"loss": loss, "accuracy": accuracy, "lr": self._lr(), "grad_norm": grad_norm}

    def train_epoch(self) -> dict[str, float]:
        self.epoch += 1
        self.overfit = max(0, (self.epoch - self.cfg["epochs"] * 0.6) * 0.5)

        losses, accs = [], []
        sleep_per_step = np.random.uniform(0.008, 0.014)  # ~3-5s 每 epoch
        log_interval = max(1, self.steps_per_epoch // 5)

        for step in range(1, self.steps_per_epoch + 1):
            m = self._step_metrics()
            losses.append(m["loss"])
            accs.append(m["accuracy"])
            if step % log_interval == 0:
                print(f"  [Epoch {self.epoch}] Step {step}/{self.steps_per_epoch} | Loss: {m['loss']:.4f} | Acc: {m['accuracy']:.4f}")
            time.sleep(sleep_per_step)

        return {
            "train_loss": float(np.mean(losses)),
            "train_accuracy": float(np.mean(accs)),
            "train_loss_std": float(np.std(losses)),
            "learning_rate": self._lr(),
        }

    def validate(self) -> dict[str, float]:
        train_loss_base = 2.5 * np.exp(-0.08 * self.epoch) + 0.15
        val_loss = max(0.1, train_loss_base + 0.08 + self.overfit * 0.03 + self.rng.normal(0, 0.02))
        train_acc_base = 1 - np.exp(-0.1 * self.epoch - 0.5)
        val_acc = min(0.995, max(0.1, train_acc_base - 0.01 - self.overfit * 0.01 + self.rng.normal(0, 0.005)))

        # 混淆矩阵
        n, samples = 10, 10_000 // 10
        cm = np.zeros((n, n), dtype=np.int64)
        for i in range(n):
            correct = int(samples * val_acc + self.rng.normal(0, samples * 0.02))
            correct = max(0, min(samples, correct))
            cm[i, i] = correct
            wrong = samples - correct
            for _ in range(wrong):
                j = (i + self.rng.choice([-1, 1])) % n if self.rng.random() < 0.8 else self.rng.integers(0, n)
                cm[i, j if j != i else (j + 1) % n] += 1

        tp, fp = np.diag(cm), cm.sum(axis=0) - np.diag(cm)
        fn = cm.sum(axis=1) - np.diag(cm)
        precision = np.mean(tp / (tp + fp + 1e-8))
        recall = np.mean(tp / (tp + fn + 1e-8))
        f1 = 2 * precision * recall / (precision + recall + 1e-8)

        return {
            "val_loss": val_loss,
            "val_accuracy": val_acc,
            "val_precision": precision,
            "val_recall": recall,
            "val_f1_macro": f1,
            "confusion_matrix": cm,
        }

    def test(self) -> dict[str, float]:
        v = self.validate()
        return {
            "test_loss": v["val_loss"] + self.rng.normal(0, 0.01),
            "test_accuracy": max(0, v["val_accuracy"] + self.rng.normal(0, 0.003)),
            "test_f1_macro": max(0, v["val_f1_macro"] + self.rng.normal(0, 0.005)),
        }


# ============================================================================
# 可视化
# ============================================================================


def _fig_to_array(fig) -> np.ndarray:
    """Matplotlib figure → RGB numpy array (H, W, C)，用于 TensorBoard add_image。"""
    fig.canvas.draw()
    rgba = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8)
    rgba = rgba.reshape(fig.canvas.get_width_height()[::-1] + (4,))
    rgb = rgba[:, :, 1:]  # ARGB → RGB
    return rgb


def plot_curves(epochs, train_losses, val_losses, train_accs, val_accs, lrs) -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    e = list(range(1, len(train_losses) + 1))
    axes[0, 0].plot(e, train_losses, "b-", label="train")
    axes[0, 0].plot(e, val_losses, "r-", label="val")
    axes[0, 0].set(xlabel="Epoch", ylabel="Loss", title="Loss")
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(e, [a * 100 for a in train_accs], "b-", label="train")
    axes[0, 1].plot(e, [a * 100 for a in val_accs], "r-", label="val")
    axes[0, 1].set(xlabel="Epoch", ylabel="Accuracy (%)", title="Accuracy")
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)

    axes[1, 0].plot(e, lrs, "g-")
    axes[1, 0].set(xlabel="Epoch", ylabel="LR", title="Learning Rate")
    axes[1, 0].grid(True, alpha=0.3)

    gap = [v - t for t, v in zip(train_losses, val_losses)]
    axes[1, 1].plot(e, gap, "purple")
    axes[1, 1].axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    axes[1, 1].set(xlabel="Epoch", ylabel="Val - Train Loss", title="Loss Gap")
    axes[1, 1].grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def plot_confusion_matrix(cm, class_names) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    fig.colorbar(im, ax=ax)
    n = len(class_names)
    ax.set(xticks=np.arange(n), yticks=np.arange(n), xticklabels=class_names, yticklabels=class_names,
           xlabel="预测", ylabel="真实", title="混淆矩阵")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    thresh = cm.max() / 2.0
    for i in range(n):
        for j in range(n):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black", fontsize=8)
    fig.tight_layout()
    return fig


def plot_roc_curves(num_classes, class_names, rng) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = plt.cm.tab10(np.linspace(0, 1, num_classes))
    mean_fpr = np.linspace(0, 1, 100)
    tprs = []
    for i in range(num_classes):
        auc_score = 0.85 + rng.random() * 0.14
        fpr = np.sort(np.concatenate([[0], rng.random(20), [1]]))
        tpr = np.sort(np.concatenate([[0], auc_score * fpr[1:-1] + rng.normal(0, 0.05, 20), [1]]))
        tpr = np.clip(tpr, 0, 1)
        interp = np.interp(mean_fpr, fpr, tpr)
        interp[0] = 0.0
        tprs.append(interp)
        ax.plot(fpr, tpr, color=colors[i], lw=1.5, label=f"{class_names[i]} (AUC={auc_score:.3f})")
    mean_tpr = np.mean(tprs, axis=0)
    mean_tpr[-1] = 1.0
    ax.plot(mean_fpr, mean_tpr, "k--", lw=2, label=f"平均 (AUC={np.trapezoid(mean_tpr, mean_fpr):.3f})")
    ax.plot([0, 1], [0, 1], "gray", linestyle=":", alpha=0.5)
    ax.set(xlabel="FPR", ylabel="TPR", title="ROC 曲线")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


# ============================================================================
# TensorBoard 日志
# ============================================================================


def _tb_log_epoch(writer, epoch, train_m, val_m, epoch_time, rng) -> None:
    writer.add_scalars("Loss", {"train": train_m["train_loss"], "val": val_m["val_loss"]}, epoch)
    writer.add_scalars("Accuracy", {"train": train_m["train_accuracy"], "val": val_m["val_accuracy"]}, epoch)
    writer.add_scalar("Metrics/val_f1", val_m["val_f1_macro"], epoch)
    writer.add_scalar("Training/lr", train_m["learning_rate"], epoch)
    writer.add_scalar("Training/epoch_time", epoch_time, epoch)
    for layer in range(5):
        writer.add_histogram(f"weights/layer{layer}", rng.normal(0, 0.05, 1000), epoch)
        writer.add_histogram(f"grads/layer{layer}", rng.normal(0, 0.1 * np.exp(-0.05 * epoch), 1000), epoch)


def _tb_log_pr(writer, epoch, num_classes, rng) -> None:
    """模拟 PR 曲线数据并写入 TensorBoard。

    add_pr_curve(tag, labels, predictions, global_step) 需要:
      labels:      真实标签 (0 或 1)
      predictions: 模型预测概率 (0~1)
    """
    n_samples = 500
    for c in range(num_classes):
        # 模拟二分类 labels: 50% 正例
        labels = rng.integers(0, 2, size=n_samples).astype(np.float32)
        # 模拟预测概率: 正例标签对应高概率，负例对应低概率
        preds = np.where(labels == 1,
                         rng.beta(5, 2, size=n_samples),   # 正例偏高的概率
                         rng.beta(2, 5, size=n_samples))   # 负例偏低的概率
        writer.add_pr_curve(f"pr/class{c}", labels, preds, global_step=epoch)


# ============================================================================
# 主流程
# ============================================================================


def main() -> None:
    config = get_config()
    rng = np.random.default_rng(config["seed"])

    print("=" * 70)
    print("🔬 KubeAI 实验追踪示例")
    print(f"  Epochs: {config['epochs']} | LR: {config['learning_rate']} | BS: {config['batch_size']}")
    print(f"  MLflow: {'开' if config['use_mlflow'] else '关'} | TensorBoard: {'开' if config['use_tensorboard'] else '关'}")
    print("=" * 70)

    os.makedirs(config["output_dir"], exist_ok=True)
    class_names = [f"类别-{i}" for i in range(10)]

    # MLflow
    if config["use_mlflow"]:
        mlflow.set_tracking_uri(config["mlflow_tracking_uri"])
        mlflow.set_experiment(config["mlflow_experiment_name"])
        run_ctx = mlflow.start_run(run_id=config["mlflow_run_id"]) if config["mlflow_run_id"] else mlflow.start_run(run_name=config["mlflow_run_name"])
    else:
        import contextlib
        run_ctx = contextlib.nullcontext()

    # TensorBoard
    writer = None
    if config["use_tensorboard"]:
        os.makedirs(config["tensorboard_log_dir"], exist_ok=True)
        writer = SummaryWriter(log_dir=config["tensorboard_log_dir"])
        print(f"\n📈 TensorBoard: {config['tensorboard_log_dir']}")

    trainer = MockTrainer(config)
    train_losses, train_accs, val_losses, val_accs, val_f1s, lrs = [], [], [], [], [], []

    with run_ctx:
        if config["use_mlflow"]:
            mlflow.log_params({
                "learning_rate": config["learning_rate"], "epochs": config["epochs"],
                "batch_size": config["batch_size"], "hidden_dim": config["hidden_dim"],
                "num_layers": config["num_layers"], "dropout": config["dropout"],
                "warmup_epochs": config["warmup_epochs"], "seed": config["seed"],
                "optimizer": "AdamW", "scheduler": "cosine_with_warmup",
                "model": f"MLP-{config['num_layers']}x{config['hidden_dim']}",
            })
        if writer:
            writer.add_hparams({k: config[k] for k in ["learning_rate", "epochs", "batch_size", "hidden_dim", "num_layers", "dropout"]}, {})

        print(f"\n🚀 训练 {config['epochs']} epochs")
        print("-" * 70)

        for epoch in range(1, config["epochs"] + 1):
            t0 = time.time()
            train_m = trainer.train_epoch()
            val_m = trainer.validate()
            epoch_time = time.time() - t0

            train_losses.append(train_m["train_loss"])
            train_accs.append(train_m["train_accuracy"])
            val_losses.append(val_m["val_loss"])
            val_accs.append(val_m["val_accuracy"])
            val_f1s.append(val_m["val_f1_macro"])
            lrs.append(train_m["learning_rate"])

            print(f"\n  Epoch {epoch}/{config['epochs']} | Train Loss: {train_m['train_loss']:.4f} | "
                  f"Train Acc: {train_m['train_accuracy']:.4f} | Val Loss: {val_m['val_loss']:.4f} | "
                  f"Val Acc: {val_m['val_accuracy']:.4f} | Val F1: {val_m['val_f1_macro']:.4f} | "
                  f"LR: {train_m['learning_rate']:.6f} | Time: {epoch_time:.1f}s")

            # MLflow
            if config["use_mlflow"]:
                mlflow.log_metrics({
                    "train_loss": train_m["train_loss"], "train_accuracy": train_m["train_accuracy"],
                    "val_loss": val_m["val_loss"], "val_accuracy": val_m["val_accuracy"],
                    "val_f1_macro": val_m["val_f1_macro"], "learning_rate": train_m["learning_rate"],
                    "epoch_time": epoch_time,
                }, step=epoch)

            # TensorBoard
            if writer:
                _tb_log_epoch(writer, epoch, train_m, val_m, epoch_time, rng)
                if epoch % 5 == 0:
                    _tb_log_pr(writer, epoch, 10, rng)

        # 测试
        print("\n" + "-" * 70)
        print("🧪 最终测试")
        test_m = trainer.test()
        print(f"  Test Loss: {test_m['test_loss']:.4f} | Test Acc: {test_m['test_accuracy']:.4f} | Test F1: {test_m['test_f1_macro']:.4f}")

        if config["use_mlflow"]:
            mlflow.log_metrics({
                "test_loss": test_m["test_loss"], "test_accuracy": test_m["test_accuracy"],
                "test_f1_macro": test_m["test_f1_macro"], "best_val_accuracy": max(val_accs),
            })
        if writer:
            writer.add_scalars("Test", {"loss": test_m["test_loss"], "accuracy": test_m["test_accuracy"], "f1": test_m["test_f1_macro"]}, 0)

        # 图表 — 直接写入 TensorBoard / MLflow，不本地保存
        print("\n📈 生成图表...")
        figs = {
            "curves": plot_curves(list(range(1, config["epochs"] + 1)), train_losses, val_losses, train_accs, val_accs, lrs),
            "confusion_matrix": plot_confusion_matrix(val_m["confusion_matrix"], class_names),
            "roc": plot_roc_curves(10, class_names, rng),
        }
        for tag, fig in figs.items():
            if writer:
                writer.add_image(f"charts/{tag}", _fig_to_array(fig), 0, dataformats="HWC")
            plt.close(fig)
            print(f"  ✓ {tag}")

        # MLflow artifact: JSON 数据
        if config["use_mlflow"]:
            cm_data = {"class_names": class_names, "matrix": val_m["confusion_matrix"].tolist()}
            mlflow.log_dict(cm_data, "confusion_matrix.json")

            summary = {
                "results": {"best_val_accuracy": max(val_accs), "test_accuracy": test_m["test_accuracy"]},
                "history": {"train_loss": train_losses, "val_loss": val_losses, "train_accuracy": train_accs, "val_accuracy": val_accs, "val_f1_macro": val_f1s, "lr": lrs},
            }
            mlflow.log_dict(summary, "summary.json")

    if writer:
        writer.close()

    print("\n" + "=" * 70)
    print(f"✅ 完成 | Best Val Acc: {max(val_accs):.4f} | Test Acc: {test_m['test_accuracy']:.4f}")
    if config["use_mlflow"]:
        print(f"📊 MLflow: {config['mlflow_tracking_uri']}")
    if config["use_tensorboard"]:
        print(f"📈 TensorBoard: uv run tensorboard --logdir={config['tensorboard_log_dir']} --port 6006")
    print("=" * 70)


if __name__ == "__main__":
    main()
