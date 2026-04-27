from typing import List, Union

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from app.core.logging_config import get_logger
from app.schemas.live_log_schema import LiveLogEntrySchema, LiveLogIngestItem
from app.services.live_log_service import live_log_service

logger = get_logger(__name__)

# No /api prefix — frontend connects directly to /live-logs
router = APIRouter(prefix="/live-logs", tags=["Live Logs"])


@router.get(
    "",
    response_model=List[LiveLogEntrySchema],
    summary="Get stored logs for a project",
)
async def get_live_logs(projectId: str = Query(...)):
    return live_log_service.get_logs(projectId)


@router.websocket("/socket")
async def live_logs_socket(websocket: WebSocket, projectId: str = Query(...)):
    await websocket.accept()
    live_log_service.connect(projectId, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket error for project %s", projectId)
    finally:
        live_log_service.disconnect(projectId, websocket)


@router.post(
    "/ingest",
    summary="Ingest logs from SDKs",
    status_code=status.HTTP_201_CREATED,
)
async def ingest_logs(payload: Union[LiveLogIngestItem, List[LiveLogIngestItem]]):
    entries = payload if isinstance(payload, list) else [payload]
    for entry in entries:
        entry_dict = entry.model_dump()
        project_id = entry_dict.pop("project_id")
        await live_log_service.add_log(project_id, entry_dict)
    return {"success": True, "ingested": len(entries)}
