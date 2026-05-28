# 镜像接口

需要 `images:read` 权限。构建操作需要 `images:build`。

## POST /api/images

创建镜像构建任务。

**请求体：**

```json
{
  "name": "my-custom-image",
  "base_image": "pytorch/pytorch:2.1-cuda12",
  "dockerfile": "FROM pytorch/pytorch:2.1-cuda12\nRUN pip install transformers",
  "build_args": {
    "VERSION": "1.0"
  }
}
```

## GET /api/images

列出镜像。

## GET /api/images/{id}

获取镜像详情，包含构建状态。

## DELETE /api/images/{id}

删除镜像记录。

## GET /api/images/{id}/logs

获取构建日志。
