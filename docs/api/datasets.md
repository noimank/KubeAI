# 数据集接口

需要 `datasets:read` 权限。写入操作需要 `datasets:write`。

## POST /api/datasets

创建数据集。

**请求体：**

```json
{
  "name": "CIFAR-10",
  "description": "CIFAR-10 图像分类数据集",
  "type": "image"
}
```

## GET /api/datasets

列出当前租户的数据集。

## GET /api/datasets/{id}

获取数据集详情，包含版本列表。

## PUT /api/datasets/{id}

更新数据集信息。

## DELETE /api/datasets/{id}

删除数据集及其所有版本。

## POST /api/datasets/{id}/versions

创建数据集版本。

## GET /api/datasets/{id}/versions

列出数据集版本。

## GET /api/datasets/{id}/versions/{version_id}/upload-url

获取文件上传预签名 URL。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 文件名 |

**响应：**

```json
{
  "success": true,
  "data": {
    "upload_url": "https://minio:9000/kubeai-datasets-xxx/...?X-Amz-..."
  }
}
```

## GET /api/datasets/{id}/versions/{version_id}/download-url

获取文件下载预签名 URL。

## POST /api/datasets/{id}/versions/{version_id}/complete

标记版本上传完成，系统自动统计文件数量和大小。
