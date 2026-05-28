# 开发环境接口

需要 `dev_environments:read` 权限。

## POST /api/dev-environments

创建开发环境。

**请求体：**

```json
{
  "name": "my-jupyter",
  "image": "jupyter/datascience-notebook:latest",
  "resources": {
    "cpu": "2",
    "memory": "4Gi"
  },
  "dataset_version_ids": ["uuid1"],
  "env_vars": {
    "JUPYTER_TOKEN": "my-token"
  }
}
```

## GET /api/dev-environments

列出开发环境。

## GET /api/dev-environments/{id}

获取开发环境详情。

## DELETE /api/dev-environments/{id}

删除开发环境。

## POST /api/dev-environments/{id}/start

启动已停止的开发环境。

## POST /api/dev-environments/{id}/stop

停止运行中的开发环境。

## GET /api/dev-environment-images

列出可用的开发环境镜像。
