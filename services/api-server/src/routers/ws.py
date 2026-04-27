"""WebSocket feed for real-time updates.

A single background task consumes Kafka topics and fans out to all connected
WebSocket clients via ConnectionManager.broadcast.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.kafka_client import consume

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


manager = ConnectionManager()


async def _make_handler(event_type: str):
    async def handle(data: dict) -> None:
        await manager.broadcast({"type": event_type, "data": data})
    return handle


async def start_ws_fanout() -> asyncio.Task:
    """Spawn the background Kafka consumers that feed the WS broadcast.

    Call from FastAPI app startup; cancel on shutdown.
    """
    contradiction_handler = await _make_handler("contradiction")
    surveillance_handler = await _make_handler("surveillance")

    async def run():
        await asyncio.gather(
            consume(
                "contradiction.found",
                "api-ws-fanout",
                contradiction_handler,
                auto_offset_reset="latest",
            ),
            consume(
                "surveillance.flag",
                "api-ws-fanout",
                surveillance_handler,
                auto_offset_reset="latest",
            ),
        )

    return asyncio.create_task(run())


@router.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; broadcasts come from the background task.
            await asyncio.sleep(30)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
