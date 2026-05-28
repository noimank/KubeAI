# Prometheus Stack - 监控 (Prometheus + Grafana)

## 部署

```bash
kubectl apply -f infra/k8s/prometheus/prometheus.yaml
```

> `prometheus.yaml` 由 `helm template` 从 kube-prometheus-stack-67.11.0 生成，包含 Prometheus、Grafana、kube-state-metrics 及所有 CRD。
> Dev 配置: Grafana NodePort 30030, Alertmanager/NodeExporter 已禁用, 数据保留 7 天。

## 验证

```bash
kubectl get pods -n monitoring
```

## 访问

| 服务 | Dev NodePort | 地址 |
|-----|-------------|------|
| Prometheus | 30090 | `http://<node-ip>:30090` |
| Grafana | 30030 | `http://<node-ip>:30030` (默认 admin/prom-operator) |

或 port-forward:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
```

## 卸载

```bash
kubectl delete -f infra/k8s/prometheus/prometheus.yaml
kubectl delete namespace monitoring
```
