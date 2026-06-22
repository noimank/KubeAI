"""
推理客户端

测试推理服务的客户端脚本，支持:
  - 从 MNIST 测试集随机抽取样本进行预测
  - 从本地图片文件进行预测
  - 对比真实标签与预测结果

用法:
    python client.py                          # 随机测试集样本
    python client.py --count 5                # 测试 5 个随机样本
    python client.py --image my_digit.png     # 指定本地图片
    python client.py --url http://localhost:8080  # 指定服务地址
"""

import argparse
import base64
import io
import json
import os
import random
import sys

import numpy as np
import requests
import torchvision.datasets as datasets
import torchvision.transforms as transforms
from PIL import Image

# 类别名（与 MNIST 对应）
CLASS_NAMES = [str(i) for i in range(10)]


def image_to_base64(image: Image.Image) -> str:
    """将 PIL Image 编码为 base64 字符串。"""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def predict_image(url: str, b64_string: str) -> dict:
    """调用推理服务。"""
    response = requests.post(
        f"{url}/predict",
        json={"image": b64_string},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def test_random_samples(url: str, data_path: str, count: int = 3) -> None:
    """从测试集随机抽取样本进行预测。"""
    print("=" * 60)
    print(f"🧪 随机测试 {count} 个样本")
    print("=" * 60)

    # 加载测试集
    transform = transforms.Compose([transforms.ToTensor()])
    test_dataset = datasets.MNIST(
        root=data_path, train=False, download=True, transform=transform
    )

    correct, total = 0, 0
    indices = random.sample(range(len(test_dataset)), count)

    for idx in indices:
        image_tensor, label = test_dataset[idx]

        # Tensor → PIL Image → base64
        pil_image = transforms.ToPILImage()(image_tensor)
        b64 = image_to_base64(pil_image)

        # 调用推理
        result = predict_image(url, b64)
        pred = result["predictions"][0]["prediction"]

        is_correct = pred["class_id"] == label
        correct += int(is_correct)
        total += 1

        status = "✅" if is_correct else "❌"
        print(
            f"  {status} 真实: {label} ({CLASS_NAMES[label]}) | "
            f"预测: {pred['class_id']} ({pred['class_name']}) | "
            f"置信度: {pred['confidence']:.4f}"
        )

        # 显示 Top-5
        top5 = result["predictions"][0].get("top5", [])
        if top5:
            top5_str = " | ".join(
                f"{t['class_name']}:{t['confidence']:.3f}" for t in top5
            )
            print(f"     Top-5: {top5_str}")

    print(f"\n📊 准确率: {correct}/{total} = {correct/total:.2%}")


def test_image_file(url: str, image_path: str) -> None:
    """对本地图片文件进行预测。"""
    print("=" * 60)
    print(f"🖼️  图片推理: {image_path}")
    print("=" * 60)

    if not os.path.exists(image_path):
        print(f"❌ 文件不存在: {image_path}", file=sys.stderr)
        sys.exit(1)

    # 读取并转换为 base64
    image = Image.open(image_path).convert("L")  # 转灰度
    b64 = image_to_base64(image)

    # 调用推理
    result = predict_image(url, b64)
    pred = result["predictions"][0]["prediction"]

    print(f"  预测: {pred['class_id']} ({pred['class_name']})")
    print(f"  置信度: {pred['confidence']:.4f}")

    top5 = result["predictions"][0].get("top5", [])
    if top5:
        print("\n  Top-5 预测:")
        for i, t in enumerate(top5, 1):
            bar = "█" * int(t["confidence"] * 50)
            print(f"    {i}. {t['class_name']} | {t['confidence']:.4f} {bar}")


def check_health(url: str) -> bool:
    """检查服务健康状态。"""
    try:
        resp = requests.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            print(f"✓ 服务健康: {url}")
            return True
    except requests.RequestException:
        pass
    print(f"❌ 无法连接服务: {url}", file=sys.stderr)
    print("   请先启动推理服务: python serve.py --port 8080", file=sys.stderr)
    return False


def show_service_info(url: str) -> None:
    """显示服务信息。"""
    try:
        resp = requests.get(url, timeout=5)
        info = resp.json()
        print(f"  服务:     {info.get('service', 'N/A')}")
        print(f"  版本:     {info.get('version', 'N/A')}")
        print(f"  框架:     {info.get('framework', 'N/A')}")
        print(f"  设备:     {info.get('device', 'N/A')}")
        print(f"  类别数:   {info.get('num_classes', 'N/A')}")
        print(f"  类别名:   {info.get('class_names', [])}")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="MNIST 推理客户端")
    parser.add_argument(
        "--url", default="http://localhost:8080", help="推理服务地址 (默认: http://localhost:8080)"
    )
    parser.add_argument(
        "--image", help="本地图片文件路径"
    )
    parser.add_argument(
        "--count", type=int, default=3, help="随机测试样本数 (默认: 3)"
    )
    parser.add_argument(
        "--data-path", default="./data", help="MNIST 数据集路径 (默认: ./data)"
    )
    args = parser.parse_args()

    # 健康检查
    if not check_health(args.url):
        sys.exit(1)

    print()
    show_service_info(args.url)
    print()

    if args.image:
        test_image_file(args.url, args.image)
    else:
        test_random_samples(args.url, args.data_path, args.count)


if __name__ == "__main__":
    main()
