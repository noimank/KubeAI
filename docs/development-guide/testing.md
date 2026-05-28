# 测试指南

## 测试架构

```
backend/tests/
├── conftest.py           # 测试配置和 Fixtures
├── unit/                 # 单元测试（40+ 文件）
│   ├── test_auth_service.py
│   ├── test_security.py
│   └── ...
└── integration/          # 集成测试（13+ 文件）
    ├── test_auth_api.py
    ├── test_tenants_api.py
    └── ...
```

## 后端测试

### 测试框架

- **pytest** + **pytest-asyncio**（`asyncio_mode = "auto"`）
- **httpx.AsyncClient** + **ASGITransport**（进程内测试，不启动服务器）
- 测试数据库使用独立的 PostgreSQL 实例

### 运行测试

```bash
# 全部测试
uv run pytest

# 仅单元测试
uv run pytest tests/unit/

# 仅集成测试
uv run pytest tests/integration/

# 单个文件
uv run pytest tests/unit/test_security.py

# 单个函数
uv run pytest tests/unit/test_security.py::test_hash_password -v

# 按关键字匹配
uv run pytest -k "test_token"

# 显示详细输出
uv run pytest -v

# 显示 print 输出
uv run pytest -s
```

### 测试配置（conftest.py）

提供以下 Fixtures：

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `event_loop` | session | 共享事件循环 |
| `async_client` | function | httpx.AsyncClient（ASGI 传输） |
| `db_session` | function | 测试数据库会话（自动回滚） |

### 编写单元测试

```python
import pytest
from app.services.auth_service import AuthService

async def test_register_user(db_session):
    service = AuthService(db_session)
    user = await service.register(
        username="testuser",
        email="test@example.com",
        password="Test123456",
    )
    assert user.username == "testuser"
    assert user.role == "annotator"
```

### 编写集成测试

```python
import pytest
from httpx import AsyncClient

async def test_login_api(async_client: AsyncClient):
    response = await async_client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "Admin123456",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
```

### CI 中的测试

CI 使用 GitHub Actions 服务容器运行测试：

```yaml
services:
  postgres:
    image: postgres:17
    env:
      POSTGRES_PASSWORD: postgres
    ports: ["5432:5432"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
```

## 前端测试

### 测试框架

- **Vitest** + jsdom 环境
- **Testing Library**（React 组件测试）
- 测试文件位于 `tests/` 下，镜像 `src/` 目录结构

### 运行测试

```bash
pnpm test           # 运行所有测试
pnpm test:watch     # 监听模式
```

### 编写组件测试

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MyComponent from "./MyComponent";

describe("MyComponent", () => {
  it("renders correctly", () => {
    render(<MyComponent />);
    expect(screen.getByText("标题")).toBeInTheDocument();
  });
});
```
