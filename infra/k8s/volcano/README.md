# Volcano - 批处理调度器

KubeAI 使用 Volcano 调度训练任务 (VCJob)。

## 部署

```bash
kubectl apply -f infra/k8s/volcano/volcano.yaml
```

> `volcano.yaml` 由 `helm template` 从 volcano-1.14.2 生成，包含 11 个 CRD、Controller、Scheduler、Admission Webhooks。
> 如需升级版本，重新渲染: `helm template volcano volcano-sh/volcano --namespace volcano-system --set custom.enableQueue=true --set custom.scheduler.replicas=1`

## 验证

```bash
kubectl get pods -n volcano-system
kubectl get queue
```

## 卸载

```bash
kubectl delete -f infra/k8s/volcano/volcano.yaml
```
