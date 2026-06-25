import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import authenticate_ws_token
from app.core.database import async_session_factory
from app.core.redis import _redis_pool
from app.core.ws_manager import get_ws_manager

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    # 浏览器 WebSocket 无法设置 Authorization 头, 走 ?token= 鉴权。
    async with async_session_factory() as db:
        user = await authenticate_ws_token(token, db, _redis_pool)
    if user is None or user.tenant_id is None:
        await websocket.close(code=4001, reason="认证失败")
        return

    user_id, tenant_id = user.id, user.tenant_id
    manager = get_ws_manager()
    await manager.connect(websocket, user_id, tenant_id)
    logger.info("ws_connected", user_id=str(user_id), tenant_id=str(tenant_id))

    try:
        while True:
            if await websocket.receive_text() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket, user_id, tenant_id)
        logger.info("ws_disconnected", user_id=str(user_id), tenant_id=str(tenant_id))
