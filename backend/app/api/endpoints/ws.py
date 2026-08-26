import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import WsUser
from app.core.ws_manager import get_ws_manager

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, user: WsUser) -> None:
    # 鉴权见 deps.authenticate_ws: 同源 Cookie, token 不经 URL 传输。
    user_id = user.id
    tenant_id = user.tenant_id
    assert tenant_id is not None  # authenticate_ws 已拒绝无租户身份, 此处仅收窄类型
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
