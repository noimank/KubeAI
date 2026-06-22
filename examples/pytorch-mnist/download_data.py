"""
MNIST 数据集下载脚本

使用 torchvision 下载 MNIST 手写数字数据集到本地 ./data/ 目录。
同时生成类别标签映射文件。

用法:
    python download_data.py                # 下载到默认 ./data/
    python download_data.py --output ./my_data  # 指定输出目录
"""

import argparse
import json
import os
import sys

import torchvision.datasets as datasets
import torchvision.transforms as transforms


def download_mnist(output_dir: str = "./data") -> None:
    """下载 MNIST 数据集并保存类别映射。"""
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("📥 下载 MNIST 数据集")
    print("=" * 60)

    # 定义简单的 ToTensor 变换
    transform = transforms.Compose([transforms.ToTensor()])

    # 下载训练集
    print("\n[1/2] 下载训练集 (60,000 张)...")
    train_dataset = datasets.MNIST(
        root=output_dir, train=True, download=True, transform=transform
    )
    print(f"  ✓ 训练集: {len(train_dataset)} 张, 图像尺寸: {train_dataset[0][0].shape}")

    # 下载测试集
    print("\n[2/2] 下载测试集 (10,000 张)...")
    test_dataset = datasets.MNIST(
        root=output_dir, train=False, download=True, transform=transform
    )
    print(f"  ✓ 测试集: {len(test_dataset)} 张, 图像尺寸: {test_dataset[0][0].shape}")

    # 类别标签映射
    classes = train_dataset.classes
    class_labels = {str(i): name for i, name in enumerate(classes)}
    labels_path = os.path.join(output_dir, "class_labels.json")
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(class_labels, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 类别标签已保存: {labels_path}")
    print(f"  类别: {class_labels}")

    # 统计
    print("\n" + "=" * 60)
    print("📊 数据集统计")
    print("=" * 60)
    print(f"  类别数:        {len(classes)}")
    print(f"  训练集样本:    {len(train_dataset):,}")
    print(f"  测试集样本:    {len(test_dataset):,}")
    print(f"  存储路径:      {os.path.abspath(output_dir)}")
    print("\n✅ MNIST 数据集下载完成！")


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 MNIST 数据集")
    parser.add_argument(
        "--output", default="./data", help="输出目录 (默认: ./data)"
    )
    args = parser.parse_args()

    try:
        download_mnist(args.output)
    except Exception as e:
        print(f"\n❌ 下载失败: {e}", file=sys.stderr)
        print("请检查网络连接后重试。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
