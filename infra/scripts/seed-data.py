"""Seed development data into KubeAI.

Usage:
    cd backend && uv run python ../infra/scripts/seed-data.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(backend_dir))

import asyncio
import uuid

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.enums import TenantStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User


async def seed() -> None:
    async with async_session_factory() as session:
        # Check if default tenant exists
        result = await session.execute(select(Tenant).where(Tenant.name == "default"))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name="default",
                display_name="默认租户",
                description="开发环境默认租户",
                status=TenantStatus.ACTIVE,
            )
            session.add(tenant)
            await session.flush()
            print(f"Created tenant: {tenant.name} ({tenant.id})")
        else:
            print(f"Tenant already exists: {tenant.name} ({tenant.id})")

        # Check if admin user exists
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        if admin is None:
            admin = User(
                username="admin",
                email="admin@163.com",
                hashed_password=hash_password("Admin@123456"),
                role=UserRole.ADMIN,
                is_active=True,
                tenant_id=tenant.id,
            )
            session.add(admin)
            print("Created admin user: admin / Admin@123456")
        else:
            print(f"Admin user already exists: {admin.username}")

        # Create test engineer user
        result = await session.execute(select(User).where(User.username == "engineer"))
        if result.scalar_one_or_none() is None:
            session.add(
                User(
                    username="engineer",
                    email="engineer@example.com",
                    hashed_password=hash_password("Engineer123456"),
                    role=UserRole.ENGINEER,
                    is_active=True,
                    tenant_id=tenant.id,
                )
            )
            print("Created engineer user: engineer / Engineer123456")

        await session.commit()
        print("\nSeed data applied successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
