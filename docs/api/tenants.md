# 租户管理接口

需要 `tenants:manage` 权限（仅 admin 角色）。

## POST /api/tenants

创建租户，同时创建 Kubernetes 命名空间和 ResourceQuota。

**请求体：**

```json
{
  "name": "team-alpha",
  "display_name": "Alpha 团队",
  "description": "Alpha 团队工作空间",
  "cpu_quota": 16.0,
  "memory_quota": 32.0,
  "gpu_quota": 4,
  "storage_quota": 100.0
}
```

## GET /api/tenants

列出所有租户。

## GET /api/tenants/{id}

获取租户详情，包含资源使用情况。

## PUT /api/tenants/{id}

更新租户信息和配额。

## DELETE /api/tenants/{id}

删除租户及其 Kubernetes 资源。

## POST /api/tenants/{id}/members

添加租户成员。

## GET /api/tenants/{id}/members

列出租户成员。

## DELETE /api/tenants/{id}/members/{user_id}

移除租户成员。

## POST /api/tenants/{id}/invitations

创建租户邀请链接。

## GET /api/invitations/{token}

通过邀请链接加入租户。
