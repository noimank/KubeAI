"""
多实验对比脚本 — 批量运行不同超参数组合，生成对比图表

本地运行:
    uv run python compare_experiments.py

该脚本会:
  1. 运行多组不同超参数的训练（模拟）
  2. 将所有实验结果记录到同一个 MLflow 实验下（各 run 独立）
  3. 可选为每个实验写入独立的 TensorBoard 日志目录
  4. 生成对比图表：不同配置的训练曲线、收敛速度、最终指标柱状图

注：多实验对比主要展示 MLflow 的多 run 对比能力。
    TensorBoard 每个实验使用独立子目录，可用 tensorboard --logdir=output/comparison 统一查看。
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

import matplotlib
import mlflow
import numpy as np
from matplotlib import pyplot as plt

matplotlib.use("Agg")

# 复用训练器
from train import MockTrainer, get_config, plot_confusion_matrix, plot_roc_curves


@dataclass(frozen=True)
class ExperimentConfig:
    """一组超参数配置。"""

    name: str
    learning_rate: float
    epochs: int
    batch_size: int
    hidden_dim: int
    num_layers: int
    dropout: float
    warmup_epochs: int


# 预定义几组对比实验
EXPERIMENTS = [
    ExperimentConfig(
        name="baseline",
        learning_rate=0.001,
        epochs=20,
        batch_size=128,
        hidden_dim=256,
        num_layers=3,
        dropout=0.3,
        warmup_epochs=3,
    ),
    ExperimentConfig(
        name="high_lr",
        learning_rate=0.01,
        epochs=20,
        batch_size=128,
        hidden_dim=256,
        num_layers=3,
        dropout=0.3,
        warmup_epochs=3,
    ),
    ExperimentConfig(
        name="large_model",
        learning_rate=0.001,
        epochs=20,
        batch_size=128,
        hidden_dim=512,
        num_layers=5,
        dropout=0.3,
        warmup_epochs=3,
    ),
    ExperimentConfig(
        name="low_dropout",
        learning_rate=0.001,
        epochs=20,
        batch_size=128,
        hidden_dim=256,
        num_layers=3,
        dropout=0.1,
        warmup_epochs=3,
    ),
    ExperimentConfig(
        name="small_batch",
        learning_rate=0.001,
        epochs=20,
        batch_size=32,
        hidden_dim=256,
        num_layers=3,
        dropout=0.3,
        warmup_epochs=3,
    ),
]


def run_single_experiment(
    exp: ExperimentConfig,
    output_dir: str,
    mlflow_tracking_uri: str,
    experiment_name: str,
    seed: int = 42,
) -> dict[str, Any]:
    """运行单个实验，返回汇总结果。"""
    print(f"\n{'='*60}")
    print(f"🧪 实验: {exp.name}")
    print(f"{'='*60}")

    config = {
        "learning_rate": exp.learning_rate,
        "epochs": exp.epochs,
        "batch_size": exp.batch_size,
        "hidden_dim": exp.hidden_dim,
        "num_layers": exp.num_layers,
        "dropout": exp.dropout,
        "warmup_epochs": exp.warmup_epochs,
        "seed": seed,
        "output_dir": os.path.join(output_dir, exp.name),
        "use_mlflow": True,
        "mlflow_tracking_uri": mlflow_tracking_uri,
        "mlflow_experiment_name": experiment_name,
        "mlflow_run_name": exp.name,
        "mlflow_run_id": None,
    }

    os.makedirs(config["output_dir"], exist_ok=True)
    class_names = [f"类别-{i}" for i in range(10)]

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(experiment_name)

    trainer = MockTrainer(config)
    rng = np.random.default_rng(seed)

    train_losses: list[float] = []
    train_accs: list[float] = []
    val_losses: list[float] = []
    val_accs: list[float] = []
    val_f1_macros: list[float] = []
    lrs: list[float] = []
    epoch_nums: list[int] = []

    with mlflow.start_run(run_name=exp.name):
        mlflow.log_params({
            "experiment_name": exp.name,
            "learning_rate": exp.learning_rate,
            "epochs": exp.epochs,
            "batch_size": exp.batch_size,
            "hidden_dim": exp.hidden_dim,
            "num_layers": exp.num_layers,
            "dropout": exp.dropout,
            "warmup_epochs": exp.warmup_epochs,
            "seed": seed,
            "optimizer": "AdamW",
            "scheduler": "cosine_with_warmup",
            "model_architecture": f"MLP-{exp.num_layers}x{exp.hidden_dim}",
        })

        for epoch in range(1, exp.epochs + 1):
            train_metrics = trainer.train_epoch()
            val_metrics = trainer.validate()

            train_losses.append(train_metrics["train_loss"])
            train_accs.append(train_metrics["train_accuracy"])
            val_losses.append(val_metrics["val_loss"])
            val_accs.append(val_metrics["val_accuracy"])
            val_f1_macros.append(val_metrics["val_f1_macro"])
            lrs.append(train_metrics["learning_rate"])
            epoch_nums.append(epoch)

            mlflow.log_metrics({
                "train_loss": train_metrics["train_loss"],
                "train_accuracy": train_metrics["train_accuracy"],
                "val_loss": val_metrics["val_loss"],
                "val_accuracy": val_metrics["val_accuracy"],
                "val_f1_macro": val_metrics["val_f1_macro"],
                "learning_rate": train_metrics["learning_rate"],
            }, step=epoch)

        test_metrics = trainer.test()
        mlflow.log_metrics({
            "test_loss": test_metrics["test_loss"],
            "test_accuracy": test_metrics["test_accuracy"],
            "test_f1_macro": test_metrics["test_f1_macro"],
            "best_val_accuracy": max(val_accs),
        })

        # 记录最终混淆矩阵图
        cm_fig = plot_confusion_matrix(val_metrics["confusion_matrix"], class_names)
        cm_path = os.path.join(config["output_dir"], "confusion_matrix.png")
        cm_fig.savefig(cm_path, dpi=150)
        plt.close(cm_fig)
        mlflow.log_artifact(cm_path)

        # ROC 曲线
        roc_fig = plot_roc_curves(10, class_names, rng)
        roc_path = os.path.join(config["output_dir"], "roc_curves.png")
        roc_fig.savefig(roc_path, dpi=150)
        plt.close(roc_fig)
        mlflow.log_artifact(roc_path)

    return {
        "name": exp.name,
        "train_losses": train_losses,
        "val_losses": val_losses,
        "train_accs": train_accs,
        "val_accs": val_accs,
        "val_f1_macros": val_f1_macros,
        "lrs": lrs,
        "epoch_nums": epoch_nums,
        "best_val_acc": max(val_accs),
        "final_test_acc": test_metrics["test_accuracy"],
        "final_test_f1": test_metrics["test_f1_macro"],
    }


def plot_comparison(results: list[dict[str, Any]], output_dir: str) -> None:
    """生成多实验对比图表。"""
    colors = plt.cm.tab10(np.linspace(0, 1, len(results)))

    # 1. Loss 对比
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    for i, r in enumerate(results):
        ax1.plot(r["epoch_nums"], r["train_losses"], color=colors[i], linestyle="-", label=f"{r['name']} (train)")
        ax1.plot(r["epoch_nums"], r["val_losses"], color=colors[i], linestyle="--", alpha=0.7)
    ax1.set(xlabel="Epoch", ylabel="Loss", title="训练/验证 Loss 对比")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    for i, r in enumerate(results):
        ax2.plot(r["epoch_nums"], [a * 100 for a in r["val_accs"]], color=colors[i], label=r["name"])
    ax2.set(xlabel="Epoch", ylabel="Accuracy (%)", title="验证准确率对比")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    path = os.path.join(output_dir, "comparison_loss_acc.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✓ Loss/Accuracy 对比图: {path}")

    # 2. 最终指标柱状图
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    names = [r["name"] for r in results]
    x = np.arange(len(names))
    width = 0.35

    best_vals = [r["best_val_acc"] * 100 for r in results]
    test_vals = [r["final_test_acc"] * 100 for r in results]
    ax1.bar(x - width / 2, best_vals, width, label="最佳验证准确率")
    ax1.bar(x + width / 2, test_vals, width, label="测试准确率")
    ax1.set(xlabel="实验", ylabel="Accuracy (%)", title="最终准确率对比")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=30, ha="right")
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis="y")

    f1_vals = [r["final_test_f1"] * 100 for r in results]
    ax2.bar(x, f1_vals, color="steelblue")
    ax2.set(xlabel="实验", ylabel="F1 Score (%)", title="测试 F1-Macro 对比")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=30, ha="right")
    ax2.grid(True, alpha=0.3, axis="y")

    fig.tight_layout()
    path = os.path.join(output_dir, "comparison_final_metrics.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✓ 最终指标对比图: {path}")


def main() -> None:
    config = get_config()
    output_dir = config["output_dir"]
    os.makedirs(output_dir, exist_ok=True)

    mlflow_tracking_uri = config["mlflow_tracking_uri"]
    experiment_name = config["mlflow_experiment_name"] + "-comparison"

    print("=" * 70)
    print("🔬 KubeAI 多实验对比示例")
    print("=" * 70)
    print(f"MLflow: {mlflow_tracking_uri}")
    print(f"实验名: {experiment_name}")
    print(f"对比组数: {len(EXPERIMENTS)}")
    print()

    results: list[dict[str, Any]] = []
    for exp in EXPERIMENTS:
        result = run_single_experiment(
            exp=exp,
            output_dir=output_dir,
            mlflow_tracking_uri=mlflow_tracking_uri,
            experiment_name=experiment_name,
        )
        results.append(result)
        time.sleep(0.5)  # 避免 MLflow 写入冲突

    print(f"\n{'='*70}")
    print("📊 生成对比图表...")
    plot_comparison(results, output_dir)

    # 打印汇总表
    print(f"\n{'='*70}")
    print("📋 实验结果汇总")
    print(f"{'='*70}")
    print(f"{'实验名':<15} {'最佳ValAcc':>12} {'测试Acc':>12} {'测试F1':>12}")
    print("-" * 55)
    for r in results:
        print(
            f"{r['name']:<15} {r['best_val_acc']*100:>11.2f}% {r['final_test_acc']*100:>11.2f}% {r['final_test_f1']*100:>11.2f}%"
        )

    print(f"\n{'='*70}")
    print("✅ 全部完成！")
    print(f"📊 在 MLflow UI 查看结果: {mlflow_tracking_uri}")
    print(f"  实验: {experiment_name}")
    print("=" * 70)


if __name__ == "__main__":
    # 让 get_config 不解析 --name 等未知参数
    import argparse

    # 临时替换 sys.argv，只保留脚本名 + 标准参数
    original_argv = sys.argv
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if not any(
        a.startswith(p) for p in ("--name", "--epochs", "--lr", "--batch", "--hidden", "--layers", "--dropout")
    )]
    try:
        main()
    finally:
        sys.argv = original_argv
