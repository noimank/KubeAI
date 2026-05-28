# 模型注册接口

需要 `models:read` 权限。写入操作需要 `models:write`。

## POST /api/models

注册模型。

**请求体：**

```json
{
  "name": "resnet50",
  "description": "ResNet-50 图像分类模型",
  "framework": "pytorch"
}
```

## GET /api/models

列出注册模型。

## GET /api/models/{id}

获取模型详情，包含所有版本。

## DELETE /api/models/{id}

删除注册模型及其所有版本。

## POST /api/models/{id}/versions

创建模型版本。

**请求体：**

```json
{
  "version": "v1",
  "description": "初始版本",
  "source": "training_job",
  "training_job_id": "uuid",
  "metrics": {
    "accuracy": 0.942,
    "f1_score": 0.938
  }
}
```

## GET /api/models/{id}/versions

列出模型版本。

## GET /api/models/{id}/versions/{version_id}

获取模型版本详情。
