# 推理服务接口

需要 `inference_services:read` 权限。管理操作需要 `inference_services:manage`。

## POST /api/inference-services

创建推理服务。

**请求体：**

```json
{
  "name": "resnet-classifier",
  "model_name": "resnet50",
  "model_version": "v3",
  "framework": "pytorch",
  "resource_config": {
    "cpu": "2",
    "memory": "8Gi",
    "gpu": 1
  },
  "autoscaling_config": {
    "min_replicas": 1,
    "max_replicas": 5,
    "target_metric": "requests_per_second",
    "target_value": 100
  }
}
```

## GET /api/inference-services

列出推理服务。

## GET /api/inference-services/{id}

获取推理服务详情。

## PUT /api/inference-services/{id}

更新推理服务配置。

## DELETE /api/inference-services/{id}

删除推理服务。

## POST /api/inference-services/{id}/stop

停止推理服务。

## POST /api/inference-services/{id}/scale

手动调整副本数。

**请求体：**

```json
{
  "replicas": 3
}
```

## POST /api/inference-proxy/{service_name}

推理代理，将请求转发到对应的推理服务端点。

**认证：** 支持通过 API Token（`Authorization: Bearer sk-...`）或 JWT Token 认证。
