# 编码规范

## 通用约定

- 所有用户面向文本使用中文（zh-CN），不使用 i18n 库
- 所有 API 响应使用 `BaseResponse[T]` 包装：`{success, message, data}`
- 后端 API 使用 snake_case；前端自动转换为 camelCase
- 提交信息使用 Conventional Commits 格式并附带 emoji 前缀

## 后端规范

### Python 版本

- Python >= 3.12
- 使用 `uv` 管理依赖（不使用 pip）

### 代码格式化

使用 Ruff 进行 lint 和格式化：

| 配置项 | 值 |
|--------|------|
| 行宽 | 120 字符 |
| 引号风格 | 双引号 |
| 目标版本 | py312 |

```bash
uv run ruff check .          # 检查
uv run ruff check --fix .    # 自动修复
uv run ruff format .         # 格式化
```

### 类型检查

使用 mypy strict 模式 + pydantic 插件：

```bash
uv run mypy app/
```

### 分层约定

```
API 端点层 (endpoints/)
  ↓ 调用
服务层 (services/)
  ↓ 调用
集成层 (integrations/) + 数据模型层 (models/)
```

- **端点层**：仅负责请求校验、权限检查、响应序列化，不包含业务逻辑
- **服务层**：封装业务逻辑，通过构造器注入 `AsyncSession`
- **集成层**：封装外部系统调用，所有 K8s 操作使用 `kubernetes_asyncio`

### 新增功能模板

新增一个功能模块需要创建以下文件：

```
backend/app/
├── models/new_model.py          # SQLAlchemy 模型
├── schemas/new_model.py         # Pydantic Schema（Create/Update/Response）
├── services/new_service.py      # 服务类
├── api/endpoints/new_module.py  # API 端点
└── alembic/versions/xxx_new_table.py  # 数据库迁移
```

在 `router.py` 中注册新路由：

```python
from app.api.endpoints import new_module
api_router.include_router(new_module.router, prefix="/new-module", tags=["new-module"])
```

### 异步约定

- 所有 K8s 调用使用 `kubernetes_asyncio`，必须 `await`
- 同步客户端（MinIO、Harbor）通过 `asyncio.to_thread()` 包装
- 数据库操作使用 async SQLAlchemy 2.0

### 依赖注入

端点使用 `deps.py` 中的依赖：

```python
from app.api.deps import CurrentUser, get_db, require_permission

@router.get("/")
async def list_items(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("items", "read")),
):
    ...
```

!!! warning "重要"
    `get_db()` 在 `app/core/database.py` 和 `app/api/deps.py` 中都有定义。**端点必须使用 `deps.py` 中的版本**。

## 前端规范

### TypeScript

- 严格模式（`strict: true`）
- 不允许未使用的变量和参数
- 使用 ES2020 目标

### 代码格式化

使用 Prettier：

| 配置项 | 值 |
|--------|------|
| 分号 | 不使用 |
| 引号 | 单引号 |
| 行宽 | 100 字符 |
| 缩进 | 2 空格 |

```bash
pnpm format    # 格式化
pnpm lint      # ESLint 检查
```

### 文件组织

- 页面组件在 `pages/` 下，每个页面一个目录
- 共享组件在 `components/` 下
- API 服务在 `services/` 下，一个模块一个文件
- 类型定义在 `types/` 下
- 状态管理在 `stores/` 下

### 状态管理

使用 Zustand，遵循 flat `create()` 模式：

```typescript
export const useMyStore = create<MyState>()((set) => ({
  data: null,
  setData: (data) => set({ data }),
}));
```

### API 调用

所有 API 调用通过 `services/` 下的模块进行，使用共享的 Axios 实例：

```typescript
import { api } from "@/services/api";

export async function getItems() {
  const { data } = await api.get("/items");
  return data;
}
```

## Git 规范

### 分支命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 功能 | `feat/feature-name` | `feat/training-jobs` |
| 修复 | `fix/bug-name` | `fix/auth-token-refresh` |
| 重构 | `refactor/name` | `refactor/api-client` |

### 提交信息

使用 Conventional Commits + emoji 前缀：

```
✨ feat: 添加训练任务创建功能
🐛 fix: 修复 Token 刷新竞态条件
♻️ refactor: 重构 API 客户端拦截器
💄 style: 迁移 Ant Design 废弃 API
📝 docs: 更新部署文档
✅ test: 添加认证服务单元测试
🔧 chore: 升级依赖版本
```
