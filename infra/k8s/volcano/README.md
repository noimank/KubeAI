# Volcano - 批处理调度器

KubeAI 使用 Volcano 调度训练任务 (VCJob)。

## 对集群其他业务的影响

> 以下仅分析部署 Volcano 对集群上**非 KubeAI 业务**的潜在影响。

| 影响项 | 是否影响其他业务 | 说明 |
|--------|:---:|------|
| Webhook 拦截范围 | 否 | 全部 4 个 Webhook 均只拦截 Volcano CRD 组资源（`batch.volcano.sh/jobs`、`scheduling.volcano.sh/queues`、`scheduling.volcano.sh/podgroups`、`topology.volcano.sh/hypernodes`、`batch.volcano.sh/cronjobs`），且已排除 `kube-system` 和 `volcano-system` 命名空间。**不拦截 K8s 原生资源**（Pod、Deployment、Job、CronJob），其他业务的任何操作均不受影响 |
| 默认调度器 | 否 | Volcano Scheduler **不会替代** default-scheduler。仅调度显式指定 `schedulerName: volcano` 的 Pod（即 VCJob 创建的训练 Pod）。普通 Pod 仍由 default-scheduler 处理，完全不受影响 |
| 调度优先级 | **需关注** | Volcano Scheduler Pod 使用 `priorityClassName: system-cluster-critical`（最高优先级）。在极端资源不足时，kubelet 为保证此 Pod 运行可能驱逐该节点上低优先级的 Pod。**但已配置 `nodeSelector: kubeai=true`，仅影响 KubeAI 标签节点的驱逐逻辑。** 如果其他业务也在 KubeAI 节点上且优先级低于 `system-cluster-critical`，理论上可能被驱逐 |
| CRDs 注册 | 否 | 注册 11 个 CRD（`jobs.batch.volcano.sh`、`queues.scheduling.volcano.sh` 等），不影响已有 API 资源 |
| RBAC | 否 | ClusterRole 仅授权访问 Volcano 相关资源，不涉及其他业务的 Secret/ConfigMap |

## 文件清单

除 `README.md` 外，本目录下所有 YAML 都是部署文件，按下表顺序使用：

| 顺序 | 文件 | 作用 |
|------|------|------|
| 1 | `00-namespace.yaml` | 创建 `volcano-system` 命名空间 |
| 2 | `volcano.yaml` | 创建 Volcano CRD、Controller、Scheduler、Admission Webhook、RBAC 和证书初始化 Job |
| 3 | `99-default-queue.yaml` | 创建 KubeAI VCJob 默认使用的 `default` Queue |

## 部署

Volcano 组件 Pod 固定使用 `nodeSelector: kubeai=true`，部署前需要至少一个可调度节点带有该标签：

```bash
kubectl label node <node-name> kubeai=true
```

```bash
kubectl apply -f infra/k8s/volcano/00-namespace.yaml
kubectl apply -f infra/k8s/volcano/volcano.yaml
kubectl wait --for=condition=Established --timeout=60s crd/jobs.batch.volcano.sh crd/queues.scheduling.volcano.sh
kubectl apply -f infra/k8s/volcano/99-default-queue.yaml
```

> `volcano.yaml` 由 `helm template` 从 volcano-1.14.2 生成，包含 11 个 CRD、Controller、Scheduler、Admission Webhooks。
> `00-namespace.yaml` 创建 `volcano-system` 命名空间。
> `99-default-queue.yaml` 创建 KubeAI VCJob 默认使用的 `default` Queue。
> Queue 是 Volcano CRD 实例，需要等待 CRD 建立后再部署。
> 如需升级版本，重新渲染: `helm template volcano volcano-sh/volcano --namespace volcano-system --set custom.enableQueue=true --set custom.scheduler.replicas=1`

## 验证

```bash
kubectl get pods -n volcano-system
kubectl get queue
kubectl rollout status deployment/volcano-admission -n volcano-system
kubectl rollout status deployment/volcano-controllers -n volcano-system
kubectl rollout status deployment/volcano-scheduler -n volcano-system
```

## 卸载

```bash
kubectl delete -f infra/k8s/volcano/99-default-queue.yaml --ignore-not-found
kubectl delete -f infra/k8s/volcano/volcano.yaml
kubectl delete -f infra/k8s/volcano/00-namespace.yaml --ignore-not-found
```
