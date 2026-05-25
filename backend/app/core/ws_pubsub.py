import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.ws_manager import get_ws_manager

logger = structlog.get_logger()

_pubsub: "WebSocketPubSub | None" = None


def get_ws_pubsub() -> "WebSocketPubSub | None":
    return _pubsub


def set_ws_pubsub(pubsub: "WebSocketPubSub | None") -> None:
    global _pubsub
    _pubsub = pubsub


class WebSocketPubSub:
    """Redis Pub/Sub 封装, 支持多副本 WebSocket 消息广播."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def publish(
        self,
        tenant_id: uuid.UUID,
        event: str,
        payload: dict[str, Any],
        target_user_id: uuid.UUID | None = None,
    ) -> None:
        message = {
            "event": event,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
            "tenant_id": str(tenant_id),
            "target_user_id": str(target_user_id) if target_user_id else None,
        }
        channel = f"kubeai:{tenant_id}:{event.split('.')[0]}"
        try:
            await self._redis.publish(channel, json.dumps(message))
        except Exception:
            logger.warning("ws_pubsub_publish_failed", channel=channel, event=event)

    async def subscribe(self) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe("kubeai:*")
        self._listener_task = asyncio.create_task(self._listener())
        logger.info("ws_pubsub_subscribed", pattern="kubeai:*")

    async def _listener(self) -> None:
        while True:
            try:
                async for message in self._pubsub.listen():  # type: ignore[union-attr]
                    if message["type"] in ("pmessage",):
                        data = json.loads(message["data"])
                        tenant_id = uuid.UUID(data["tenant_id"])
                        target_user_id = data.get("target_user_id")
                        manager = get_ws_manager()
                        if target_user_id and target_user_id != "None":
                            await manager.send_to_user(uuid.UUID(target_user_id), tenant_id, data)
                        else:
                            await manager.send_to_tenant(tenant_id, data)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("ws_pubsub_listener_error", exc_info=e)
                await asyncio.sleep(1)
                try:
                    if self._pubsub:
                        await self._pubsub.psubscribe("kubeai:*")
                except Exception:
                    pass

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None
        logger.info("ws_pubsub_closed")
