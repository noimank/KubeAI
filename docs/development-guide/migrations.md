# 数据库迁移

## 概述

KubeAI 使用 Alembic 管理 PostgreSQL 数据库迁移，迁移文件位于 `backend/alembic/versions/`。

当前共有 38+ 迁移文件，覆盖从初始表创建到最新功能的所有数据库变更。

## 常用命令

```bash
cd backend/

# 查看当前迁移状态
uv run alembic current

# 查看迁移历史
uv run alembic history

# 应用所有迁移
uv run alembic upgrade head

# 回退一个版本
uv run alembic downgrade -1

# 回退到指定版本
uv run alembic downgrade <revision>

# 升级到指定版本
uv run alembic upgrade <revision>

# 自动生成迁移（基于模型变更）
uv run alembic revision --autogenerate -m "add_new_table"

# 手动创建空迁移
uv run alembic revision -m "custom_data_migration"
```

## 创建迁移

### 自动生成

修改 SQLAlchemy 模型后，运行自动迁移生成：

```bash
uv run alembic revision --autogenerate -m "描述信息"
```

Alembic 会自动检测模型的变更并生成迁移脚本。

!!! warning "注意"
    自动生成的迁移需要手动检查，确保：
    - 没有遗漏的变更
    - 数据类型正确
    - 索引和外键正确

### 手动创建

对于数据迁移或复杂变更，手动创建迁移：

```bash
uv run alembic revision -m "seed_default_data"
```

### 迁移模板

```python
"""add new table

Revision ID: xxxx
Revises: yyyy
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "xxxx"
down_revision = "yyyy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "new_table",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("new_table")
```

## 最佳实践

1. **每个迁移只做一件事**：避免在一个迁移中混合多个不相关的变更
2. **总是提供 downgrade**：确保迁移可以安全回退
3. **数据迁移要小心**：大量数据操作可能锁表，考虑分批处理
4. **测试迁移**：在开发环境测试升级和回退
5. **命名清晰**：迁移描述要准确反映变更内容

## 迁移在部署中的角色

- **开发环境**：后端启动时 `migration.enabled=true` 自动运行迁移
- **生产环境**：建议在部署前手动运行迁移，或在 CI 中运行
