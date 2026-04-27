"""
Project Routes
CRUD for projects and API token management.
All routes require authentication.
"""

from fastapi import APIRouter, HTTPException, Depends, status

from app.dependencies.auth_dependency import get_current_user
from app.schemas.project_schema import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TokenCreateRequest,
)
from app.services.project_service import project_service
from app.models.project_model import project_helper, token_helper
from app.utils.response_handler import create_response
from app.core.logging_config import get_logger
from app.core.config import settings

logger = get_logger(__name__)


router = APIRouter(prefix="/api/projects", tags=["Projects"])


# ============================================
# Project CRUD
# ============================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    request: ProjectCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    project = await project_service.create_project(
        name=request.name,
        owner_id=current_user["id"],
        description=request.description,
        language=request.language,
    )
    data = project_helper(project)
    data["token_count"] = 0
    return create_response(success=True, message="Project created", data=data)


@router.get(
    "",
    summary="List all projects for the authenticated user",
)
async def list_projects(current_user: dict = Depends(get_current_user)):
    projects = await project_service.list_projects(owner_id=current_user["id"])
    data = []
    for p in projects:
        d = project_helper(p)
        d["token_count"] = p.get("token_count", 0)
        data.append(d)
    return create_response(success=True, message="Projects retrieved", data=data)


@router.get(
    "/{project_id}",
    summary="Get a single project",
)
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    project = await project_service.get_project(project_id, current_user["id"])
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )
    data = project_helper(project)
    data["token_count"] = project.get("token_count", 0)
    return create_response(success=True, message="Project retrieved", data=data)


@router.get(
    "/{project_id}/github/webhook-url",
    summary="Generate the GitHub webhook URL for a project",
)
async def get_webhook_url(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    project = await project_service.get_project(project_id, current_user["id"])
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )
    base = settings.INGESTION_SERVER_BASE_URL.rstrip("/")
    webhook_url = f"https://marin-nonadjudicated-ernestina.ngrok-free.dev/api/v1/webhook/{project_id}/github/"
    return create_response(
        success=True,
        message="Webhook URL generated",
        data={"webhookUrl": webhook_url},
    )


@router.patch(
    "/{project_id}",
    summary="Update a project",
)
async def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(success=False, message="No fields to update"),
        )
    project = await project_service.update_project(
        project_id, current_user["id"], update_data
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )
    return create_response(
        success=True, message="Project updated", data=project_helper(project)
    )


@router.delete(
    "/{project_id}",
    summary="Delete a project and all its tokens",
)
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    deleted = await project_service.delete_project(project_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )
    return create_response(success=True, message="Project deleted")


# ============================================
# Token Management
# ============================================


@router.post(
    "/{project_id}/tokens",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new API token for a project",
)
async def create_token(
    project_id: str,
    request: TokenCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        token_doc, plain_token = await project_service.create_token(
            project_id=project_id,
            owner_id=current_user["id"],
            label=request.label,
        )
    except ValueError as e:
        err_msg = str(e)
        # Distinguish "project not found" vs "active token exists"
        if "active token already exists" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=create_response(success=False, message=err_msg),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message=err_msg),
        )

    # Return full token only at creation — masked everywhere else
    data = {
        "id": str(token_doc["_id"]),
        "project_id": token_doc["project_id"],
        "label": token_doc["label"],
        "token": plain_token,
        "token_masked": f"{token_doc.get('token_prefix', '')}...{token_doc.get('token_suffix', '')}",
        "is_active": token_doc.get("is_active", True),
        "created_at": token_doc["created_at"].isoformat(),
    }

    return create_response(
        success=True,
        message="Token created. Copy it now — it won't be shown again.",
        data=data,
    )


@router.get(
    "/{project_id}/tokens",
    summary="List all tokens for a project (masked)",
)
async def list_tokens(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    # Verify project ownership
    project = await project_service.get_project(project_id, current_user["id"])
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Project not found"),
        )

    tokens = await project_service.list_tokens(project_id, current_user["id"])
    data = [token_helper(t) for t in tokens]
    return create_response(success=True, message="Tokens retrieved", data=data)


@router.patch(
    "/{project_id}/tokens/{token_id}/disable",
    summary="Disable an active API token (must disable before generating a new one)",
)
async def disable_token(
    project_id: str,
    token_id: str,
    current_user: dict = Depends(get_current_user),
):
    disabled = await project_service.disable_token(token_id, current_user["id"])
    if not disabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Token not found or already disabled"),
        )
    return create_response(success=True, message="Token disabled")


@router.delete(
    "/{project_id}/tokens/{token_id}",
    summary="Revoke (delete) an API token",
)
async def delete_token(
    project_id: str,
    token_id: str,
    current_user: dict = Depends(get_current_user),
):
    deleted = await project_service.delete_token(token_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_response(success=False, message="Token not found"),
        )
    return create_response(success=True, message="Token revoked")
