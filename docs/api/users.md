# 用户管理接口

需要 `users:read` 权限。管理操作需要 `users:manage` 权限。

## GET /api/users

获取用户列表。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码 |
| `page_size` | int | 每页条数 |
| `role` | string | 按角色过滤 |
| `is_active` | bool | 按状态过滤 |
| `search` | string | 搜索用户名/邮箱 |

## GET /api/users/{id}

获取用户详情。

## PUT /api/users/{id}

更新用户信息。

**请求体：**

```json
{
  "email": "string",
  "role": "engineer",
  "is_active": true
}
```

## PUT /api/users/{id}/password

修改用户密码。

**请求体：**

```json
{
  "old_password": "string",
  "new_password": "string"
}
```

## DELETE /api/users/{id}

软删除用户（设置 `deleted_at`）。
