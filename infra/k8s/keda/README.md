# KEDA - 事件驱动自动扩缩容

KubeAI 使用 KEDA 为推理服务提供基于自定义指标的自动扩缩容 (ScaledObject CRD)。

## 部署

```bash
kubectl apply -f infra/k8s/keda/keda.yaml
```

> `keda.yaml` 由 `helm template` 从 KEDA Chart 渲染，包含 Operator、Metrics Server、CRDs 及 Webhook。

## 验证

```bash
kubectl get pods -n keda
kubectl get scaledobjects.keda.sh -A
```

## 卸载

```bash
kubectl delete -f infra/k8s/keda/keda.yaml
kubectl delete namespace keda
```
