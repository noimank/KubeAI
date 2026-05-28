# DCGM Exporter - GPU 指标采集

NVIDIA DCGM Exporter 暴露 GPU 利用率、显存、温度、功耗等 Prometheus 指标。

> 仅在有 GPU 节点的集群中需要。开发环境 (Docker Desktop) 无需安装。

## 部署

```bash
kubectl apply -f infra/k8s/dcgm-exporter/dcgm-exporter.yaml
```

> `dcgm-exporter.yaml` 由 `helm template` 从 dcgm-exporter-3.6.1 生成，含 ServiceMonitor (15s 采集间隔) 和 GPU 节点容忍。

## 验证

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=dcgm-exporter
```

## Grafana Dashboard

安装后导入 DCGM Dashboard (ID: `12239` 或 `15454`)。

## 卸载

```bash
kubectl delete -f infra/k8s/dcgm-exporter/dcgm-exporter.yaml
```
