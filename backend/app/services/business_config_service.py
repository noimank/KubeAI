"""业务配置管理服务：CRUD。"""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.business_config import BusinessConfig
from app.schemas.business_config import BusinessConfigCreate, BusinessConfigUpdate


class BusinessConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, tenant_id: uuid.UUID, user_id: uuid.UUID, data: BusinessConfigCreate) -> dict[str, Any]:
        existing = await self.db.execute(
            select(BusinessConfig).where(BusinessConfig.tenant_id == tenant_id, BusinessConfig.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise ConflictException("配置名称已存在")

        config = BusinessConfig(
            tenant_id=tenant_id,
            created_by=user_id,
            name=data.name,
            description=data.description,
            env_vars=data.env_vars,
        )
        self.db.add(config)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException("配置名称已存在") from exc

        await self.db.refresh(config)
        return self._to_dict(config)

    async def list_configs(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        base = select(BusinessConfig).where(BusinessConfig.tenant_id == tenant_id)
        count_base = select(func.count()).select_from(BusinessConfig).where(BusinessConfig.tenant_id == tenant_id)

        if search:
            like = f"%{search}%"
            base = base.where(BusinessConfig.name.ilike(like) | BusinessConfig.description.ilike(like))
            count_base = count_base.where(BusinessConfig.name.ilike(like) | BusinessConfig.description.ilike(like))

        total_result = await self.db.execute(count_base)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        result = await self.db.execute(base.order_by(BusinessConfig.updated_at.desc()).offset(offset).limit(page_size))
        items = [self._to_dict(row) for row in result.scalars().all()]

        return items, total

    async def get(self, tenant_id: uuid.UUID, config_id: uuid.UUID) -> dict[str, Any]:
        config = await self._get_or_404(tenant_id, config_id)
        return self._to_dict(config)

    async def update(self, tenant_id: uuid.UUID, config_id: uuid.UUID, data: BusinessConfigUpdate) -> dict[str, Any]:
        config = await self._get_or_404(tenant_id, config_id)

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != config.name:
            existing = await self.db.execute(
                select(BusinessConfig).where(
                    BusinessConfig.tenant_id == tenant_id,
                    BusinessConfig.name == update_data["name"],
                    BusinessConfig.id != config_id,
                )
            )
            if existing.scalar_one_or_none():
                raise ConflictException("配置名称已存在")

        stmt = (
            update(BusinessConfig)
            .where(BusinessConfig.id == config_id, BusinessConfig.tenant_id == tenant_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        await self.db.flush()
        await self.db.refresh(config)
        return self._to_dict(config)

    async def delete(self, tenant_id: uuid.UUID, config_id: uuid.UUID) -> None:
        config = await self._get_or_404(tenant_id, config_id)
        await self.db.delete(config)
        await self.db.flush()

    async def _get_or_404(self, tenant_id: uuid.UUID, config_id: uuid.UUID) -> BusinessConfig:
        result = await self.db.execute(
            select(BusinessConfig).where(BusinessConfig.id == config_id, BusinessConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise NotFoundException("业务配置不存在")
        return config

    @staticmethod
    def _to_dict(config: BusinessConfig) -> dict[str, Any]:
        return {
            "id": config.id,
            "tenant_id": config.tenant_id,
            "created_by": config.created_by,
            "name": config.name,
            "description": config.description,
            "env_vars": config.env_vars,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }
