# 训练任务接口

需要 `training_jobs:read` 权限。写入操作需要 `training_jobs:write`。

## POST /api/training-jobs

创建训练任务。

**请求体：**

```json
{
  "name": "resnet-training",
  "framework": "pytorch",
  "image": "pytorch/pytorch:2.1-cuda12",
  "command": "python train.py --epochs 100 --lr 0.001",
  "resources": {
    "cpu": "4",
    "memory": "16Gi",
    "gpu": 2
  },
  "dataset_version_id": "uuid",
  "env_vars": {
    "BATCH_SIZE": "32"
  }
}
```

## GET /api/training-jobs

列出训练任务。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 按状态过滤 |
| `framework` | string | 按框架过滤 |

## GET /api/training-jobs/{id}

获取训练任务详情。

## DELETE /api/training-jobs/{id}

删除训练任务（仅限非 Running 状态）。

## POST /api/training-jobs/{id}/stop

停止运行中的训练任务。

## GET /api/training-jobs/{id}/logs

获取训练日志（分页）。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码 |
| `page_size` | int | 每页条数 |

## GET /api/training-jobs/{id}/logs/stream

SSE 流式获取训练日志。

**事件格式：**

```
event: log
data: {"timestamp": "2025-01-01T00:00:00", "message": "Epoch 1/100, Loss: 0.5"}
```

认证通过查询参数 `?token=<access_token>` 进行。
