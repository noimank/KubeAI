"""KubeAI → Casdoor 角色正向同步.

Casdoor 的用户-角色关系存储在 Role 对象的 users 数组 ("org/username" 列表)上,
改角色即改写涉及的 kubeai_* 角色并整体更新. OIDC 登录时 oauth_service 会以
Casdoor 角色回写本地, 因此角色变更必须先推送成功, 否则会被登录静默覆盖回去.
"""

import structlog

from app.core.clients import get_casdoor_client
from app.core.exceptions import ExternalServiceException
from app.integrations.casdoor.client import KUBEAI_ROLE_PREFIX, CasdoorClient
from app.models.enums import UserRole
from app.models.user import User

logger = structlog.get_logger()


async def _resolve_casdoor_user(casdoor: CasdoorClient, external_id: str) -> str:
    """把本地存储的 external_id (OIDC sub) 归一化为 Casdoor 角色成员标识 owner/name.

    sub 随 Casdoor 版本/配置可能是 owner/name, 也可能是用户 id (如 UUID/数字),
    而角色的 users 数组只认 owner/name, 写入前必须解析.
    """
    if "/" in external_id:
        return external_id
    user = await casdoor.get_user_by_ref(external_id)
    if not user or not user.get("owner") or not user.get("name"):
        raise ExternalServiceException(f"无法在 Casdoor 中解析用户: {external_id}")
    return f"{user['owner']}/{user['name']}"


async def sync_role_to_casdoor(user: User, new_role: UserRole, client: CasdoorClient | None = None) -> None:
    """将本地角色变更实时推送到 Casdoor (仅三方登录账号, 本地账号直接跳过).

    目标角色 kubeai_{role} 不存在视为 Casdoor 配置缺失, 显式失败避免静默分叉.
    """
    if user.auth_provider != "oidc" or not user.external_id:
        return

    casdoor = client or get_casdoor_client()
    casdoor_user = await _resolve_casdoor_user(casdoor, user.external_id)
    target_role_name = f"{KUBEAI_ROLE_PREFIX}{new_role.value}"

    roles = await casdoor.get_kubeai_roles()
    if not any(r.get("name") == target_role_name for r in roles):
        raise ExternalServiceException(f"Casdoor 中不存在角色 {target_role_name}, 请先在 Casdoor 应用下创建")

    for role in roles:
        members = list(role.get("users") or [])
        should_contain = role.get("name") == target_role_name
        if (casdoor_user in members) == should_contain:
            continue
        if should_contain:
            members.append(casdoor_user)
        else:
            members.remove(casdoor_user)
        role["users"] = members
        await casdoor.update_role(role)
        logger.info(
            "casdoor_role_synced",
            casdoor_user=casdoor_user,
            casdoor_role=role["name"],
            member=should_contain,
        )
