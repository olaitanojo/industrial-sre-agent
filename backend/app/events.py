import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from .schemas import EventMessage


class EventBroker:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._history: list[EventMessage] = []

    @property
    def history(self) -> list[EventMessage]:
        return self._history[-100:]

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        for event in self.history:
            await websocket.send_json(event.model_dump(mode="json"))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        message = EventMessage(event=event, timestamp=datetime.now(UTC), payload=payload)
        self._history.append(message)
        if len(self._history) > 100:
            self._history.pop(0)
        async with self._lock:
            recipients = list(self._connections)
        for websocket in recipients:
            try:
                await websocket.send_json(message.model_dump(mode="json"))
            except Exception:
                await self.disconnect(websocket)
