"""
Chat Routes
Protected endpoints for encrypted project retrieval and HTTP chat streaming.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.logging_config import get_logger
from app.dependencies.auth_dependency import get_current_user
from app.models.chat_model import chat_summary_helper
from app.schemas.chat_schema import ChatStreamRequest
from app.services.chat_service import chat_service
from app.services.chat_stream_service import chat_stream_service
from app.services.project_service import project_service
from app.utils.response_handler import create_response

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get(
    "/{project_id}",
    summary="List all chats for a specific project",
)
async def list_project_chats(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    project = await project_service.get_project(project_id, current_user["id"])
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )

    chats = await chat_service.list_project_chats(project_id, current_user["id"])
    data = {
        "project_id": project_id,
        "project_name": project.get("name", ""),
        "chats": [chat_summary_helper(chat) for chat in chats],
    }
    return create_response(success=True, message="Chats retrieved", data=data)


@router.get(
    "/{project_id}/{chat_id}",
    summary="Load minimal chat context for a specific project chat",
)
async def get_project_chat(
    project_id: str,
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    project = await project_service.get_project(project_id, current_user["id"])
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )

    chat = await chat_service.get_chat(project_id, chat_id, current_user["id"])
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Chat not found"),
        )

    chat_context = await chat_service.get_chat_context(
        project_id=project_id,
        chat_id=chat_id,
        owner_id=current_user["id"],
    )
    return create_response(
        success=True,
        message="Chat context retrieved",
        data={"chat_context": chat_context},
    )


@router.post(
    "/{project_id}/{chat_id}/close",
    summary="Close a chat and trigger background vague-context summarization",
)
async def close_chat(
    project_id: str,
    chat_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    project = await project_service.get_project(project_id, current_user["id"])
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )

    chat = await chat_service.get_chat(project_id, chat_id, current_user["id"])
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Chat not found"),
        )

    logger.info(
        "chat close requested (project=%s, chat=%s, user=%s, message_count=%d)",
        project_id,
        chat_id,
        current_user["id"],
        chat.get("message_count", 0),
    )
    background_tasks.add_task(
        chat_stream_service.summarize_and_update_vague_context,
        project_id=project_id,
        owner_id=current_user["id"],
        chat_id=chat_id,
    )
    return create_response(
        success=True,
        message="Chat close acknowledged; summarization in progress",
    )


@router.post(
    "/stream",
    summary="Stream a chat response over chunked HTTP",
)
async def stream_chat_http(
    request: ChatStreamRequest,
    current_user: dict = Depends(get_current_user),
):
    stream = chat_stream_service.iter_sse_chunks(
        current_user=current_user,
        request=request,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
