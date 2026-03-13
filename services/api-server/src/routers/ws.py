"""WebSocket feed for real-time updates."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Listen for Redis stream events and forward to WebSocket
        redis = await get_redis()
        last_id = "$"

        while True:
            try:
                # Read from contradiction.found stream
                messages = await redis.xread(
                    {"contradiction.found": last_id},
                    count=10,
                    block=5000,
                )
                for stream_name, entries in messages:
                    for msg_id, fields in entries:
                        last_id = msg_id
                        data = json.loads(fields.get("data", "{}"))
                        await websocket.send_json({
                            "type": "contradiction",
                            "data": data,
                        })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket stream error: {e}")
                await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
