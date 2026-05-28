# KServe - 模型推理服务

KubeAI 使用 KServe 管理 InferenceService CRD，支持模型部署、自动扩缩容、金丝雀发布。

## 部署

```bash
# 1. CRDs (必须先安装)
kubectl apply -f infra/k8s/kserve/kserve-crd.yaml

# 2. Controller + Webhooks
kubectl apply -f infra/k8s/kserve/kserve.yaml

# 3. ServingRuntimes (Standard 模式必需)
kubectl apply --server-side -f https://github.com/kserve/kserve/releases/download/v0.17.0/kserve-cluster-resources.yaml
```

> `kserve-crd.yaml` / `kserve.yaml` 由 `helm template` 从 KServe v0.17.0 OCI Chart 渲染。
> Standard (RawDeployment) 模式，无需 Knative Serving。

## 前置条件

- cert-manager (KServe Webhook 需要证书管理)

## 验证

```bash
kubectl get pods -n kserve
kubectl get crd inferenceservices.serving.kserve.io
```

## 卸载

```bash
kubectl delete -f infra/k8s/kserve/kserve.yaml
kubectl delete -f infra/k8s/kserve/kserve-crd.yaml
kubectl delete namespace kserve
```
