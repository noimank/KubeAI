# 实验接口

需要 `experiments:read` 权限。

## GET /api/experiments

列出实验（从 MLflow 同步）。

## GET /api/experiments/{id}

获取实验详情。

## GET /api/experiments/{id}/runs

列出实验运行记录。

## POST /api/experiments/compare

对比多个实验的参数和指标。

**请求体：**

```json
{
  "experiment_ids": ["id1", "id2", "id3"]
}
```

## POST /api/experiments/{id}/reproduce

将实验复现为新的训练任务。
