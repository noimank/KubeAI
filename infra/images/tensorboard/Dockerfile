# 平台 TensorBoard sidecar 镜像 — 镜像地址通过 TENSORBOARD_IMAGE 配置注入.
#
# 极简设计: 只装 tensorboard + setuptools + 一个非 root 用户, 总镜像 < 200MB.
# setuptools 提供 tensorboard 启动时依赖的 pkg_resources (python:3.12-slim 不预装).
# 不预装 tensorflow/torch — trainer 容器负责这些.
#
# 用法: 由平台 build_vcjob 在 trainer Pod 注入 sidecar 容器,
# 共享 emptyDir 卷 /kubeai/tensorboard, 读取 trainer 写的 tfevents.

# Build: docker build -t hub.uimpcloud.com/kubeai/kubeai-tensorboard:latest  -f infra/images/tensorboard/Dockerfile .

FROM python:3.12-slim-bookworm

RUN pip install --no-cache-dir 'setuptools<70' tensorboard==2.18.0

# 非 root 用户, 与 dev_pod 保持一致 (UID 1000)
RUN useradd -u 1000 -m -s /bin/bash tensorboard

USER 1000:1000
WORKDIR /kubeai/tensorboard

EXPOSE 6006

# Default entrypoint for standalone runs. When injected as a VCJob sidecar,
# build_vcjob overrides `command` to add `--path_prefix=/tensorboard/<hex>` so
# TensorBoard serves under the APISIX-routed subpath.
# --host=0.0.0.0 makes the server reachable via the ClusterIP Service.
CMD ["tensorboard", "--logdir=/kubeai/tensorboard", "--host=0.0.0.0", "--port=6006"]
