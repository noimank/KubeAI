"""
MNIST 推理 HTTP 服务

基于 Flask 的轻量推理服务，加载训练好的 PyTorch 模型，
提供 REST API 进行手写数字识别。

本地运行:
    python serve.py --port 8080

KubeAI 平台:
    构建为容器镜像后通过 KServe InferenceService 部署，
    KubeAI 会自动注入 MLFLOW_TRACKING_URI 等环境变量。

端点:
    GET  /          — 服务信息
    GET  /health    — 健康检查
    POST /predict   — 单张/批量推理
"""

import argparse
import base64
import io
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from train import MNISTCNN  # 复用模型定义

# Flask 是可选依赖（仅推理服务需要）
try:
    from flask import Flask, request, jsonify
except ImportError:
    print("请安装 Flask: pip install flask", file=sys.stderr)
    sys.exit(1)

# ============================================================================
# 模型加载
# ============================================================================

# 全局模型实例（模块级单例）
_model: MNISTCNN | None = None
_class_names: list[str] = []
_device: torch.device | None = None
_model_version: str = "1.0.0"


def load_model(model_path: str, device: torch.device | None = None) -> MNISTCNN:
    """加载训练好的模型。"""
    global _device
    if device is None:
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = MNISTCNN(num_classes=10)
    state_dict = torch.load(model_path, map_location=_device, weights_only=True)
    model.load_state_dict(state_dict)
    model.to(_device)
    model.eval()
    return model


def load_class_names(data_path: str) -> list[str]:
    """加载类别标签。"""
    labels_path = os.path.join(data_path, "class_labels.json")
    if os.path.exists(labels_path):
        with open(labels_path, "r", encoding="utf-8") as f:
            class_labels = json.load(f)
        return [class_labels[str(i)] for i in range(10)]
    return [str(i) for i in range(10)]


# ============================================================================
# 图像预处理
# ============================================================================


def preprocess_image(image_data: bytes) -> torch.Tensor:
    """将原始图像字节转换为模型输入 Tensor。

    支持: PNG/JPEG 任意尺寸 → 28x28 灰度 → [0,1] → 归一化
    """
    image = Image.open(io.BytesIO(image_data)).convert("L")  # 灰度
    image = image.resize((28, 28), Image.LANCZOS)

    # 转为 numpy 数组并归一化
    img_array = np.array(image, dtype=np.float32) / 255.0
    img_array = (img_array - 0.1307) / 0.3081  # MNIST 标准归一化

    # 转为 Tensor: (H, W) → (1, 1, 28, 28)
    tensor = torch.from_numpy(img_array).unsqueeze(0).unsqueeze(0)
    return tensor


def preprocess_base64(b64_string: str) -> torch.Tensor:
    """解码 base64 字符串并预处理。"""
    # 去除可能的 data:image/...;base64, 前缀
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    image_data = base64.b64decode(b64_string)
    return preprocess_image(image_data)


# ============================================================================
# 推理
# ============================================================================


@torch.no_grad()
def predict(tensor: torch.Tensor) -> list[dict]:
    """对单个 Tensor 执行推理，返回预测结果列表。"""
    tensor = tensor.to(_device)
    output = _model(tensor)
    probs = F.softmax(output, dim=1)

    results = []
    for i in range(probs.size(0)):
        top5_idx = probs[i].topk(5).indices.cpu().numpy()
        top5_prob = probs[i].topk(5).values.cpu().numpy()
        predictions = [
            {
                "class_id": int(idx),
                "class_name": _class_names[idx],
                "confidence": float(conf),
            }
            for idx, conf in zip(top5_idx, top5_prob)
        ]
        results.append({
            "prediction": predictions[0],  # Top-1
            "top5": predictions,
        })

    return results


# ============================================================================
# Flask 应用
# ============================================================================

app = Flask(__name__)


@app.route("/", methods=["GET"])
def info():
    """服务信息。"""
    return jsonify({
        "service": "mnist-cnn-inference",
        "version": _model_version,
        "framework": "PyTorch",
        "device": str(_device),
        "num_classes": 10,
        "class_names": _class_names,
    })


@app.route("/health", methods=["GET"])
def health():
    """健康检查。"""
    return jsonify({"status": "healthy", "timestamp": time.time()})


@app.route("/predict", methods=["POST"])
def predict_endpoint():
    """推理端点。

    请求格式 (JSON):
        # 方式 1: base64 编码图片
        {"image": "<base64_string>"}

        # 方式 2: 批量
        {"images": ["<base64_string>", ...]}

    响应格式 (JSON):
        {
            "predictions": [
                {
                    "prediction": {"class_id": 7, "class_name": "7", "confidence": 0.98},
                    "top5": [...]
                }
            ]
        }
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求体必须为 JSON 格式"}), 400

    # 批量推理
    if "images" in data:
        images = data["images"]
        if not isinstance(images, list):
            return jsonify({"error": "'images' 应为字符串数组"}), 400
        try:
            tensors = [preprocess_base64(img) for img in images]
        except Exception as e:
            return jsonify({"error": f"图片解码失败: {str(e)}"}), 400
        batch = torch.cat(tensors, dim=0)

    # 单张推理
    elif "image" in data:
        try:
            batch = preprocess_base64(data["image"])
        except Exception as e:
            return jsonify({"error": f"图片解码失败: {str(e)}"}), 400

    else:
        return jsonify({"error": "请提供 'image' 或 'images' 字段"}), 400

    # 执行推理
    try:
        results = predict(batch)
    except Exception as e:
        return jsonify({"error": f"推理失败: {str(e)}"}), 500

    return jsonify({
        "predictions": results,
        "inference_time_ms": round(time.time() * 1000),
    })


# ============================================================================
# 入口
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="MNIST CNN 推理服务")
    parser.add_argument("--port", type=int, default=8080, help="服务端口 (默认: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认: 0.0.0.0)")
    parser.add_argument("--model", default="./output/mnist_cnn.pt", help="模型路径")
    parser.add_argument("--data-path", default="./data", help="类别标签路径")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"❌ 模型文件不存在: {args.model}", file=sys.stderr)
        print("   请先运行 train.py 训练模型。", file=sys.stderr)
        sys.exit(1)

    # 加载模型
    global _model, _class_names
    print("=" * 60)
    print("🔮 MNIST CNN 推理服务")
    print("=" * 60)
    _model = load_model(args.model)
    _class_names = load_class_names(args.data_path)
    print(f"  模型:     {args.model}")
    print(f"  设备:     {_device}")
    print(f"  类别:     {_class_names}")

    # 启动服务
    print(f"\n🚀 服务启动: http://{args.host}:{args.port}")
    print(f"   健康检查: http://{args.host}:{args.port}/health")
    print(f"   推理端点: POST http://{args.host}:{args.port}/predict")
    print(f"\n   按 Ctrl+C 停止服务")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
