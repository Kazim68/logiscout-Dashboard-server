import json
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import WebSocket

from app.core.logging_config import get_logger

logger = get_logger(__name__)

MAX_LOGS_PER_PROJECT = 500


class LiveLogService:
    def __init__(self):
        self._store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_LOGS_PER_PROJECT))
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    def get_logs(self, project_id: str) -> List[dict]:
        return list(reversed(self._store.get(project_id, [])))

    async def add_log(self, project_id: str, entry: dict) -> dict:
        if not entry.get("id"):
            entry["id"] = uuid.uuid4().hex
        if not entry.get("timestamp"):
            entry["timestamp"] = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._store[project_id].append(entry)
        await self._broadcast(project_id, entry)
        return entry

    async def _broadcast(self, project_id: str, entry: dict) -> None:
        connections = self._connections.get(project_id)
        if not connections:
            return

        dead: List[WebSocket] = []
        message = json.dumps(entry)

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            connections.discard(ws)
            logger.debug("Removed dead WebSocket for project %s", project_id)

    def connect(self, project_id: str, websocket: WebSocket) -> None:
        self._connections[project_id].add(websocket)
        logger.info("WebSocket connected for project %s (%d total)", project_id, len(self._connections[project_id]))

    def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        self._connections[project_id].discard(websocket)
        logger.info("WebSocket disconnected for project %s (%d remaining)", project_id, len(self._connections[project_id]))


live_log_service = LiveLogService()
