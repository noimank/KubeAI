# KEDA - 事件驱动自动扩缩容

KubeAI 使用 KEDA 为推理服务提供基于自定义指标的自动扩缩容 (ScaledObject CRD)。

## 对集群其他业务的影响

> 以下仅分析部署 KEDA 对集群上**非 KubeAI 业务**的潜在影响。

| 影响项 | 是否影响其他业务 | 说明 |
|--------|:---:|------|
| APIService 注册 | **是** | 注册 `v1beta1.external.metrics.k8s.io` APIService，KEDA Metrics Server 成为集群外部指标的唯一提供方。若 KEDA 卸载或 Metrics Server 全部挂掉，集群中所有使用 `external.metrics.k8s.io` 的 HPA（任何命名空间）均查询超时。**绝大多数 HPA 使用 `metrics.k8s.io`（CPU/内存），不受影响。** 仅影响显式配置了外部指标的 HPA |
| Webhook 拦截范围 | 否 | ValidatingWebhook 仅拦截 `keda.sh` 组资源（ScaledObject/ScaledJob）的 CREATE/UPDATE，不拦截原生 K8s 资源（Pod、Deployment 等）。`failurePolicy: Ignore`，即使 KEDA Pod 全部挂掉，API Server 也仅跳过校验直接放行 |
| CRDs 注册 | 否 | 仅注册 KEDA 专属 CRD，不影响已有 API 资源 |
| 默认调度器 | 否 | KEDA 不注册独立 Scheduler，不替换 default-scheduler，不影响任何 Pod 调度 |
| 节点资源抢占 | 否 | 已配置 `nodeSelector: kubeai=true`，仅调度到 KubeAI 节点 |

## 文件清单

除 `README.md` 外，本目录下所有 YAML 都是部署文件，按下表顺序使用：

| 顺序 | 文件 | 作用 |
|------|------|------|
| 1 | `00-namespace.yaml` | 创建 `keda` 命名空间 |
| 2 | `keda.yaml` | 创建 KEDA CRD、Operator、Metrics Server、Admission Webhook、APIService 和 RBAC |

## 部署

KEDA 组件 Pod 固定使用 `nodeSelector: kubeai=true`，部署前需要至少一个可调度节点带有该标签：

```bash
kubectl label node <node-name> kubeai=true
```

```bash
kubectl apply -f infra/k8s/keda/00-namespace.yaml
kubectl apply --server-side -f infra/k8s/keda/keda.yaml
```

> `00-namespace.yaml` 创建 `keda` 命名空间。
> `keda.yaml` 由 `helm template` 从 KEDA Chart 渲染，包含 Operator、Metrics Server、CRDs 及 Webhook。
> KEDA CRD schema 较大，必须使用 server-side apply，避免 `kubectl.kubernetes.io/last-applied-configuration` annotation 超过 Kubernetes 256KiB 限制。
> KEDA webhook/metrics server 证书由 KEDA operator 自动创建和轮转，不依赖 cert-manager。

## 验证

```bash
kubectl get pods -n keda
kubectl rollout status deployment/keda-operator -n keda
kubectl rollout status deployment/keda-operator-metrics-apiserver -n keda
kubectl rollout status deployment/keda-admission-webhooks -n keda
kubectl get scaledobjects.keda.sh -A
```

## 卸载

```bash
kubectl delete -f infra/k8s/keda/keda.yaml
kubectl delete -f infra/k8s/keda/00-namespace.yaml --ignore-not-found
```
