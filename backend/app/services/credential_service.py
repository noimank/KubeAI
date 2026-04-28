import logging
import uuid

from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.secret import create_secret, delete_secret, get_secret, make_secret_name

logger = logging.getLogger(__name__)


class CredentialService:
    def store_credential(self, tenant_id: uuid.UUID, credential_name: str, credential_data: dict[str, str]) -> str:
        namespace = make_namespace_name(str(tenant_id))
        secret_name = make_secret_name(str(tenant_id), credential_name)
        create_secret(namespace, secret_name, credential_data)
        logger.info("Stored credential %s for tenant %s", credential_name, tenant_id)
        return secret_name

    def get_credential(self, tenant_id: uuid.UUID, credential_name: str) -> dict[str, str] | None:
        namespace = make_namespace_name(str(tenant_id))
        secret_name = make_secret_name(str(tenant_id), credential_name)
        return get_secret(namespace, secret_name)

    def delete_credential(self, tenant_id: uuid.UUID, credential_name: str) -> None:
        namespace = make_namespace_name(str(tenant_id))
        secret_name = make_secret_name(str(tenant_id), credential_name)
        delete_secret(namespace, secret_name)
        logger.info("Deleted credential %s for tenant %s", credential_name, tenant_id)
