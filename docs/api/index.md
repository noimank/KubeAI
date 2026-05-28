# API 参考

KubeAI 后端提供 RESTful API，所有接口统一使用 `/api` 前缀，响应格式为 `BaseResponse<T>`。

## 通用约定

### 响应格式

所有 API 返回统一的 JSON 格式：

```json
{
  "success": true,
  "message": "操作成功",
  "data": { ... }
}
```

### 错误响应

```json
{
  "success": false,
  "message": "错误描述（中文）",
  "data": null
}
```

### 认证

除注册/登录外，所有接口需要在请求头中携带 JWT Token：

```
Authorization: Bearer <access_token>
```

### 键名约定

| 位置 | 格式 | 说明 |
|------|------|------|
| 请求参数 | snake_case | 后端 Python 约定 |
| 响应数据 | snake_case | 后端自动保持 |
| 前端发送 | camelCase | 前端 Axios 拦截器自动转换为 snake_case |
| 前端接收 | camelCase | 前端 Axios 拦截器自动转换为 camelCase |

### 分页

列表接口支持分页参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页条数 |

分页响应格式：

```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

## HTTP 状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未授权（Token 无效或过期） |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 422 | 参数校验失败 / 配额超出 |
| 500 | 服务器内部错误 |
| 502 | 外部服务异常 |

## 模块索引

| 模块 | 说明 | 详细文档 |
|------|------|----------|
| 认证 | 登录、注册、Token 刷新 | [auth.md](auth.md) |
| 用户管理 | 用户 CRUD 和角色管理 | [users.md](users.md) |
| 租户管理 | 租户和配额管理 | [tenants.md](tenants.md) |
| 数据集 | 数据集和版本管理 | [datasets.md](datasets.md) |
| 训练任务 | 模型训练任务管理 | [training-jobs.md](training-jobs.md) |
| 推理服务 | 模型推理部署 | [inference.md](inference.md) |
| 模型注册 | 模型版本管理 | [models.md](models.md) |
| 实验跟踪 | MLflow 实验管理 | [experiments.md](experiments.md) |
| 数据标注 | 标注项目和任务 | [annotations.md](annotations.md) |
| 开发环境 | Jupyter 开发环境 | [dev-environments.md](dev-environments.md) |
| 镜像管理 | 容器镜像构建 | [images.md](images.md) |
| 集群监控 | 资源和 GPU 监控 | [monitoring.md](monitoring.md) |
