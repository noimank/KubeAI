import uuid
from contextlib import suppress
from typing import Any

from fastapi import WebSocket

_manager: "ConnectionManager | None" = None


def get_ws_manager() -> "ConnectionManager":
    if _manager is None:
        raise RuntimeError("WebSocket manager not initialized")
    return _manager


def set_ws_manager(manager: "ConnectionManager") -> None:
    global _manager
    _manager = manager


class ConnectionManager:
    """管理 WebSocket 连接, 按 tenant_id -> user_id 分组."""

    MAX_CONNECTIONS_PER_USER = 5

    def __init__(self) -> None:
        # tenant_id → user_id → list of (websocket, order_index)
        self._connections: dict[uuid.UUID, dict[uuid.UUID, list[WebSocket]]] = {}
        self._order: dict[uuid.UUID, dict[uuid.UUID, list[int]]] = {}
        self._counter = 0

    async def connect(self, websocket: WebSocket, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await websocket.accept()
        if tenant_id not in self._connections:
            self._connections[tenant_id] = {}
            self._order[tenant_id] = {}
        if user_id not in self._connections[tenant_id]:
            self._connections[tenant_id][user_id] = []
            self._order[tenant_id][user_id] = []

        conns = self._connections[tenant_id][user_id]
        orders = self._order[tenant_id][user_id]

        # 超过最大连接数时关闭最早连接
        if len(conns) >= self.MAX_CONNECTIONS_PER_USER:
            oldest_idx = 0
            oldest_ws = conns.pop(oldest_idx)
            orders.pop(oldest_idx)
            with suppress(Exception):
                await oldest_ws.close(code=4002, reason="超出最大连接数限制")

        conns.append(websocket)
        orders.append(self._counter)
        self._counter += 1

    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        if tenant_id not in self._connections:
            return
        if user_id not in self._connections[tenant_id]:
            return

        conns = self._connections[tenant_id][user_id]
        orders = self._order[tenant_id][user_id]
        try:
            idx = conns.index(websocket)
            conns.pop(idx)
            orders.pop(idx)
        except ValueError:
            pass

        if not conns:
            del self._connections[tenant_id][user_id]
            del self._order[tenant_id][user_id]
        if not self._connections[tenant_id]:
            del self._connections[tenant_id]
            del self._order[tenant_id]

    async def send_to_user(self, user_id: uuid.UUID, tenant_id: uuid.UUID, message: dict[str, Any]) -> None:
        if tenant_id not in self._connections:
            return
        if user_id not in self._connections[tenant_id]:
            return

        dead: list[int] = []
        conns = self._connections[tenant_id][user_id]
        for i, ws in enumerate(conns):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(i)

        for i in reversed(dead):
            conns.pop(i)
            self._order[tenant_id][user_id].pop(i)

        if not conns:
            del self._connections[tenant_id][user_id]
            del self._order[tenant_id][user_id]
        if tenant_id in self._connections and not self._connections[tenant_id]:
            del self._connections[tenant_id]
            del self._order[tenant_id]

    async def send_to_tenant(self, tenant_id: uuid.UUID, message: dict[str, Any]) -> None:
        if tenant_id not in self._connections:
            return
        for user_id in list(self._connections[tenant_id].keys()):
            await self.send_to_user(user_id, tenant_id, message)

    @property
    def connection_count(self) -> int:
        return sum(len(conns) for users in self._connections.values() for conns in users.values())
