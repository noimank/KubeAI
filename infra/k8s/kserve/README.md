# KServe - 模型推理服务

> **本项目推理不走 KServe 运行时**：平台推理服务由后端直接创建自有 Pod（自定义镜像 Deployment + ClusterIP
> Service + APISIX 路由，见 `backend/app/integrations/k8s/inference_route.py`）。
> 本目录仅部署 KServe 控制面（InferenceService CRD + Controller + Istio 入站），不部署
> ClusterServingRuntime 推理运行时镜像，供后续模型服务按需接入。

## 对集群其他业务的影响

> 以下仅分析部署 KServe 对集群上**非 KubeAI 业务**的潜在影响。

| 影响项 | 是否影响其他业务 | 说明 |
|--------|:---:|------|
| Pod Mutator Webhook | **需关注** | KServe 的 `pod-mutator` 拦截**所有命名空间** Pod 的 CREATE 操作，`failurePolicy: Fail`，但通过 `objectSelector` 精确匹配——仅处理带 `serving.kserve.io/inferenceservice` 标签的 Pod（KServe 自动注入）。**普通 Pod 没有此标签，API Server 不会发给 Webhook，不受影响。** 但如果 KServe Webhook 证书过期或 Service 不可达，API Server 调用 Webhook 超时会增加 Pod 创建延迟（默认 10s 超时），**不会阻塞**无标签的 Pod |
| InferenceService Mutator/Validator | 否 | 仅拦截 `serving.kserve.io` 组资源（InferenceService CREATE/UPDATE）。其他业务的 Deployment/StatefulSet 完全不受影响 |
| CRDs 注册 | 否 | 仅注册 KServe 专属 CRD，不影响已有 API 资源，kubectl 正常 |
| cert-manager 依赖 | 否 | KServe 依赖 cert-manager 签发 Webhook TLS 证书。若无 cert-manager，Webhook Pod 无法启动，但不影响其他业务 Pod |
| Istio 网关 | **需关注** | istio-ingressgateway 占用 NodePort；已有 Istio 时只需创建 Gateway，无 Istio 时安装最小化配置。详见下文 |

## 前置条件

| 依赖 | 必须 | 说明 |
|------|:---:|------|
| cert-manager | ✅ | KServe Webhook TLS 证书签发 |
| Istio | ✅ | KServe Standard 模式使用 Istio IngressClass 路由推理流量 |
| KEDA | 否 | 推理服务弹性伸缩（按需部署 `infra/k8s/keda/`） |
| Volcano | 否 | 训练任务调度（与 KServe 无关） |

## 文件清单

```
infra/k8s/kserve/
├── README.md
├── 00-namespace.yaml              # 创建 kserve 命名空间
├── kserve-crd.yaml                # KServe CRD (server-side apply)
├── kserve.yaml                    # KServe Controller + Webhooks + RBAC
│
└── istio/                         # Istio 入站链路
    ├── istio-operator.yaml        #   IstioOperator 配置 (manifest 生成源)
    ├── generate.sh                #   在有网机器上执行 → 生成 istio-manifest.yaml
    ├── istio-manifest.yaml        #   生成的纯 K8s YAML (kubectl apply 即用)
    ├── kserve-gateway.yaml        #   Gateway + IngressClass
    └── install.sh                 #   一键 kubectl apply 部署 (无需 istioctl)
```

## 部署顺序

```bash
# ============================================================
# 0. 前置: cert-manager
# ============================================================
# KServe Webhook 需要 cert-manager 签发 TLS 证书
# 如未安装:
#   kubectl apply -f infra/k8s/cert-manager/cert-manager.yaml
#   kubectl wait --for=condition=available deployment/cert-manager -n cert-manager --timeout=120s

# ============================================================
# 1. Istio (KServe 推理流量入站)
# ============================================================
# 确保 istio-manifest.yaml 已生成 (如未生成，先在有网机器上执行 generate.sh):
#   bash infra/k8s/kserve/istio/generate.sh
#
# 方式 A: 一键部署 (推荐)
bash infra/k8s/kserve/istio/install.sh

# 方式 B: 手动部署
#   kubectl apply -f infra/k8s/kserve/istio/istio-manifest.yaml
#   kubectl apply -f infra/k8s/kserve/istio/kserve-gateway.yaml

# 如集群已有 Istio:
#   SKIP_ISTIO=1 bash infra/k8s/kserve/istio/install.sh

# 验证
kubectl get pods -n istio-system
kubectl get ingressclass istio
kubectl get gateway kserve-ingress-gateway -n kserve

# ============================================================
# 2. KServe
# ============================================================
# Namespace
kubectl apply -f infra/k8s/kserve/00-namespace.yaml

# CRDs (必须先安装)
kubectl apply --server-side -f infra/k8s/kserve/kserve-crd.yaml
kubectl wait --for=condition=Established --timeout=60s \
  crd/inferenceservices.serving.kserve.io \
  crd/servingruntimes.serving.kserve.io \
  crd/clusterservingruntimes.serving.kserve.io

# Controller + Webhooks
kubectl apply -f infra/k8s/kserve/kserve.yaml
```

> **说明**: 
> - `00-namespace.yaml` 创建 `kserve` 命名空间。
> - `kserve-crd.yaml` / `kserve.yaml` 基于 KServe v0.17.0 生成。
> - KServe CRD schema 较大，必须使用 server-side apply，避免 `last-applied-configuration` annotation 超过 256KiB 限制。
> - Standard (RawDeployment) 模式，无需 Knative Serving。
> - 不部署 ClusterServingRuntime 推理运行时（平台推理使用自有 Pod；如后续需要 KServe 运行时，
>   由 `kserve-1.17` helm template 重新生成 cluster-resources 并自行补推对应镜像）。

## 推理服务入站链路

```
外部请求
  │
  ▼
istio-ingressgateway (istio-system, NodePort/LoadBalancer)
  │
  ▼
Gateway "kserve-ingress-gateway" (kserve namespace)
  │  └─ VirtualService (KServe 自动创建，按 host 路由)
  ▼
InferenceService Pod (推理容器)
```

Istio 安装后，KServe 创建的 InferenceService 会自动生成对应的 VirtualService，无需手动配置路由。

## 验证

```bash
# Istio
kubectl get pods -n istio-system
kubectl get svc istio-ingressgateway -n istio-system

# KServe
kubectl get pods -n kserve
kubectl get crd inferenceservices.serving.kserve.io
kubectl rollout status deployment/kserve-controller-manager -n kserve
```

## 卸载

```bash
# 1. KServe
kubectl delete -f infra/k8s/kserve/kserve.yaml
kubectl delete -f infra/k8s/kserve/kserve-crd.yaml
kubectl delete -f infra/k8s/kserve/00-namespace.yaml --ignore-not-found

# 2. Istio Gateway
kubectl delete -f infra/k8s/kserve/istio/kserve-gateway.yaml --ignore-not-found

# 3. Istio (如不再需要)
kubectl delete -f infra/k8s/kserve/istio/istio-manifest.yaml --ignore-not-found
kubectl delete namespace istio-system --ignore-not-found
```
