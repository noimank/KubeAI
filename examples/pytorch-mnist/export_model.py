"""
模型导出脚本

将训练好的 PyTorch 模型导出为 TorchScript 和 ONNX 格式，
适配 KServe 推理部署。

用法:
    python export_model.py                          # 导出全部格式
    python export_model.py --model ./output/mnist_cnn.pt  # 指定模型路径
"""

import argparse
import os
import sys

import torch

from train import MNISTCNN  # 复用模型定义


def export_torchscript(model: torch.nn.Module, output_path: str) -> None:
    """导出 TorchScript (traced) 格式。"""
    print("\n[1/2] 导出 TorchScript...")
    model.eval()

    # 使用示例输入 trace 模型
    example_input = torch.randn(1, 1, 28, 28)
    with torch.no_grad():
        traced = torch.jit.trace(model, example_input)

    traced.save(output_path)
    print(f"  ✓ 已保存: {output_path}")

    # 验证
    loaded = torch.jit.load(output_path)
    with torch.no_grad():
        out1 = model(example_input)
        out2 = loaded(example_input)
    assert torch.allclose(out1, out2, atol=1e-5), "TorchScript 输出不一致！"
    print(f"  ✓ 验证通过: 输出一致")
    print(f"  文件大小: {os.path.getsize(output_path) / 1024:.1f} KB")


def export_onnx(model: torch.nn.Module, output_path: str) -> None:
    """导出 ONNX 格式。"""
    print("\n[2/2] 导出 ONNX...")
    model.eval()

    example_input = torch.randn(1, 1, 28, 28)
    torch.onnx.export(
        model,
        example_input,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
    )
    print(f"  ✓ 已保存: {output_path}")
    print(f"  文件大小: {os.path.getsize(output_path) / 1024:.1f} KB")

    # 验证
    import onnx
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    print(f"  ✓ ONNX 模型验证通过")


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 PyTorch 模型为 TorchScript / ONNX")
    parser.add_argument(
        "--model",
        default="./output/mnist_cnn.pt",
        help="训练好的模型路径 (默认: ./output/mnist_cnn.pt)",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="导出目录 (默认: ./output)",
    )
    parser.add_argument(
        "--format",
        choices=["torchscript", "onnx", "all"],
        default="all",
        help="导出格式 (默认: all)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"❌ 模型文件不存在: {args.model}", file=sys.stderr)
        print("   请先运行 train.py 训练模型。", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 60)
    print("📦 模型导出")
    print("=" * 60)
    print(f"  源模型:  {args.model}")
    print(f"  导出目录: {args.output_dir}")
    print(f"  格式:    {args.format}")

    # 加载模型（state_dict 格式）
    model = MNISTCNN(num_classes=10)
    model.load_state_dict(torch.load(args.model, map_location="cpu", weights_only=True))
    print(f"\n✓ 模型加载成功")

    if args.format in ("torchscript", "all"):
        export_torchscript(model, os.path.join(args.output_dir, "mnist_cnn_traced.pt"))

    if args.format in ("onnx", "all"):
        try:
            export_onnx(model, os.path.join(args.output_dir, "mnist_cnn.onnx"))
        except ImportError:
            print("\n⚠ 跳过 ONNX 导出: 请先安装 onnx 包 (pip install onnx onnxruntime)")
        except Exception as e:
            print(f"\n⚠ ONNX 导出失败: {e}")

    print("\n✅ 模型导出完成！")
    print(f"\n📁 产物文件:")
    for f in os.listdir(args.output_dir):
        fpath = os.path.join(args.output_dir, f)
        if os.path.isfile(fpath):
            print(f"   {f} ({os.path.getsize(fpath) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
