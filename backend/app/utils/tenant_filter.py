import uuid
from typing import Any

from sqlalchemy import Select

from app.models.base import TenantMixin


def apply_tenant_filter(query: Select[Any], model_class: type, tenant_id: uuid.UUID) -> Select[Any]:
    if issubclass(model_class, TenantMixin):
        return query.where(model_class.tenant_id == tenant_id)
    return query
