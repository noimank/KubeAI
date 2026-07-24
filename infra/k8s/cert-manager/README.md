# cert-manager — 证书管理

cert-manager 为 Harbor、APISIX 等组件的 Webhook 自动签发和管理 TLS 证书。

## 对集群其他业务的影响

| 影响项 | 是否影响其他业务 | 说明 |
|--------|:---:|------|
| APIService 注册 | 否 | cert-manager 不注册 APIService |
| Webhook 拦截范围 | 否 | Webhook 仅拦截 cert-manager CRD (Certificate/Issuer 等) 的 CREATE/UPDATE，不拦截原生 K8s 资源 |
| CRDs 注册 | 否 | 仅注册 6 个 cert-manager 专属 CRD，不影响已有 API 资源 |
| 默认调度器 | 否 | 不注册独立 Scheduler，不替换 default-scheduler |
| 节点资源抢占 | 否 | 仅限制 `kubernetes.io/os: linux`，公用组件不绑定特定节点，可按集群资源自由调度 |

## 前置条件

| 依赖 | 必须 | 说明 |
|------|:---:|------|
| - | - | 无额外依赖，可直接部署 |

## 文件清单

| 文件 | 作用 |
|------|------|
| `cert-manager.yaml` | cert-manager v1.16.1 完整部署 (CRD + Controller + Webhook + CA Injector + RBAC) |

> `cert-manager.yaml` 已包含 Namespace 创建 (`cert-manager`)，无需单独的 `00-namespace.yaml`。

## 部署

```bash
kubectl apply -f infra/k8s/cert-manager/cert-manager.yaml

# 等待所有组件就绪
kubectl wait --for=condition=available deployment/cert-manager -n cert-manager --timeout=120s
kubectl wait --for=condition=available deployment/cert-manager-cainjector -n cert-manager --timeout=120s
kubectl wait --for=condition=available deployment/cert-manager-webhook -n cert-manager --timeout=120s
```

## 验证

```bash
kubectl get pods -n cert-manager
kubectl get crd | grep cert-manager
```

## 卸载

```bash
kubectl delete -f infra/k8s/cert-manager/cert-manager.yaml
```

> ⚠️ 卸载前确保没有其他组件依赖 cert-manager（如 Harbor / APISIX 的 Certificate 资源）。
