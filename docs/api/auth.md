# 认证接口

## POST /api/auth/register

注册新用户。

!!! note "注意"
    需要配置 `ALLOW_USER_REGISTRATION=true` 才能开放注册。

**请求体：**

```json
{
  "username": "string",       // 必填，3-50 字符
  "email": "string",          // 必填，合法邮箱
  "password": "string",       // 必填，6-50 字符
  "tenant_id": "string"       // 可选，指定加入的租户
}
```

**响应：**

```json
{
  "success": true,
  "message": "注册成功",
  "data": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "role": "annotator"
  }
}
```

## POST /api/auth/login

用户登录。

**请求体：**

```json
{
  "username": "string",
  "password": "string"
}
```

**响应：**

```json
{
  "success": true,
  "message": "登录成功",
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 1800
  }
}
```

**错误情况：**

| 条件 | 状态码 | 消息 |
|------|--------|------|
| 用户名或密码错误 | 401 | 用户名或密码错误 |
| 账户已锁定 | 403 | 账户已锁定，请 15 分钟后重试 |
| 用户已禁用 | 403 | 账户已禁用 |

## POST /api/auth/refresh

刷新 Token。

**请求体：**

```json
{
  "refresh_token": "eyJ..."
}
```

**响应：**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 1800
  }
}
```

## POST /api/auth/logout

用户登出，将当前 Token 加入黑名单。

**请求头：** `Authorization: Bearer <access_token>`

**响应：**

```json
{
  "success": true,
  "message": "登出成功"
}
```

## GET /api/auth/me

获取当前用户信息。

**响应：**

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "role": "engineer",
    "tenant_id": "uuid",
    "is_active": true
  }
}
```

## GET /api/auth/oidc/{provider}

发起 OIDC 登录，重定向到身份提供商。

## GET /api/auth/oidc/{provider}/callback

OIDC 回调，完成认证并返回 JWT Token。
