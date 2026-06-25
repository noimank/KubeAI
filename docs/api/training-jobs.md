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

## WS /api/training-jobs/{id}/logs/ws

WebSocket 实时推送训练日志(运行中任务)。WebSocket 为升级连接, nginx 直接透传, 不受代理缓冲影响(SSE 在双层 nginx 下会被缓冲, 故改用 WS)。

**消息格式：**

```
{"line": "2025-01-01T00:00:00 Epoch 1/100, Loss: 0.5"}
```

- 客户端可定期发送文本帧 `ping`, 服务端回 `{"type":"pong"}`, 用于 half-open 链路检测。
- 任务不存在 / 尚未提交 / 无关联 Pod 时, 服务端发送 `{"error":"..."}` 后关闭连接。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `token` | string | 必填, access token(浏览器 WebSocket 无法设置 Authorization 头) |
| `pod_name` | string | 可选, 分布式任务指定 Pod |
| `tail_lines` | int | 可选, 首批历史日志行数, 默认 100 |
