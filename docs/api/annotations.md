# 标注接口

需要 `annotations:read` 权限。管理操作需要 `annotations:manage`。

## POST /api/annotations

创建标注项目。

**请求体：**

```json
{
  "name": "猫狗分类标注",
  "project_type": "image_classification",
  "label_config": {
    "labels": ["猫", "狗"]
  },
  "dataset_id": "uuid",
  "dataset_version_id": "uuid"
}
```

## GET /api/annotations

列出标注项目。

## GET /api/annotations/{id}

获取标注项目详情。

## DELETE /api/annotations/{id}

删除标注项目。

## GET /api/annotations/{id}/tasks

列出标注任务。

## POST /api/annotations/{id}/tasks/assign

分配标注任务给标注员。

**请求体：**

```json
{
  "task_ids": ["uuid1", "uuid2"],
  "assignee_id": "uuid"
}
```

## POST /api/annotations/{id}/tasks/{task_id}/cancel

取消一个已完成的标注。任务回到 in_progress，删除 `annotations/<file>.json`，清空 `task.result`。

## POST /api/annotations/{id}/export

导出标注数据。

## GET /api/datasets/{dataset_id}/versions/{version_id}/files/{file_name}/annotation

读单文件标注 JSON（不存在返回 404）。
