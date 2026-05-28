# 监控接口

需要 `monitoring:read` 权限。

## GET /api/monitoring/cluster

获取集群概览指标。

**响应：**

```json
{
  "success": true,
  "data": {
    "node_count": 5,
    "cpu_total": 64,
    "cpu_used": 32.5,
    "memory_total": 256,
    "memory_used": 128.3,
    "gpu_total": 8,
    "gpu_used": 4,
    "running_pods": 45
  }
}
```

## GET /api/monitoring/nodes

获取各节点资源使用详情。

## GET /api/monitoring/tenants/{tenant_id}

获取指定租户的资源使用情况。

## GET /api/monitoring/gpu

获取 GPU 详细指标。

## GET /api/monitoring/alerts

获取告警列表。
