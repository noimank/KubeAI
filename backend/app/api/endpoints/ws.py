import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.redis import _redis_pool
from app.core.security import decode_token
from app.core.token_blacklist import TokenBlacklistService
from app.core.ws_manager import get_ws_manager

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    # 1. 认证
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4001, reason="认证失败")
        return

    if payload.get("type") != "access":
        await websocket.close(code=4001, reason="无效的 Token 类型")
        return

    jti = payload.get("jti")
    if not jti:
        await websocket.close(code=4001, reason="无效的 Token")
        return

    # 检查 Token 黑名单
    if _redis_pool is not None:
        blacklist = TokenBlacklistService(_redis_pool)
        if await blacklist.is_revoked(jti):
            await websocket.close(code=4001, reason="Token 已被吊销")
            return

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        await websocket.close(code=4001, reason="无效的 Token")
        return

    tenant_id_str = payload.get("tenant_id")
    if not tenant_id_str:
        await websocket.close(code=4001, reason="缺少租户信息")
        return
    try:
        tenant_id = uuid.UUID(tenant_id_str)
    except ValueError:
        await websocket.close(code=4001, reason="无效的租户信息")
        return

    # 2. 注册连接
    manager = get_ws_manager()
    await manager.connect(websocket, user_id, tenant_id)
    logger.info("ws_connected", user_id=str(user_id), tenant_id=str(tenant_id))

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket, user_id, tenant_id)
        logger.info("ws_disconnected", user_id=str(user_id), tenant_id=str(tenant_id))
