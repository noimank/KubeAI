import logging

from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.secret import create_secret, delete_secret, get_secret, make_secret_name

logger = logging.getLogger(__name__)


class CredentialService:
    async def store_credential(self, tenant_name: str, credential_name: str, credential_data: dict[str, str]) -> str:
        namespace = make_namespace_name(tenant_name)
        secret_name = make_secret_name(tenant_name, credential_name)
        await create_secret(namespace, secret_name, credential_data)
        logger.info("Stored credential %s for tenant %s", credential_name, tenant_name)
        return secret_name

    async def get_credential(self, tenant_name: str, credential_name: str) -> dict[str, str] | None:
        namespace = make_namespace_name(tenant_name)
        secret_name = make_secret_name(tenant_name, credential_name)
        return await get_secret(namespace, secret_name)

    async def delete_credential(self, tenant_name: str, credential_name: str) -> None:
        namespace = make_namespace_name(tenant_name)
        secret_name = make_secret_name(tenant_name, credential_name)
        await delete_secret(namespace, secret_name)
        logger.info("Deleted credential %s for tenant %s", credential_name, tenant_name)
