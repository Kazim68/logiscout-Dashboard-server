"""
Project Model
Defines the Project and API Token document structures for MongoDB.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class ProjectModel(BaseModel):
    """
    Project document model for MongoDB.

    Attributes:
        id: MongoDB ObjectId (auto-generated)
        name: Project name
        description: Optional project description
        owner_id: User ID who owns this project
        status: active | inactive
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    description: Optional[str] = None
    language: str = "python"  # "python" or "nodejs"
    owner_id: str  # References users._id
    status: str = "active"
    webhook_base_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "name": "Payment Service",
                "description": "Handles payment processing",
                "language": "python",
                "owner_id": "507f1f77bcf86cd799439011",
                "status": "active",
            }
        }


class APITokenModel(BaseModel):
    """
    API Token document model for MongoDB.

    Tokens are stored in plain text with a unique index for O(1) lookups.
    The full token is only returned at creation time; list endpoints show
    a masked version (prefix...suffix).

    Attributes:
        id: MongoDB ObjectId
        project_id: Parent project ID
        owner_id: User ID who owns this token
        label: Human-friendly label (e.g. "Production", "Staging")
        token: The plain-text token (uniquely indexed)
        token_prefix: First 8 chars for display (e.g. "lgs_Ab3x")
        token_suffix: Last 4 chars for display
        created_at: Creation timestamp
        last_used_at: Last usage timestamp (updated on log ingestion)
    """

    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    owner_id: str
    label: str = "Default"
    token: str  # Plain-text token (uniquely indexed in MongoDB)
    token_prefix: str  # e.g. "lgs_Ab3x"
    token_suffix: str  # e.g. "r8t4"
    is_active: bool = True  # False = disabled; must disable before generating a new token
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


def project_helper(project: dict) -> dict:
    """Format a project document for API responses."""
    return {
        "id": str(project["_id"]),
        "name": project.get("name", ""),
        "description": project.get("description", ""),
        "language": project.get("language", "python"),
        "owner_id": project.get("owner_id", ""),
        "status": project.get("status", "active"),
        "created_at": project.get("created_at", datetime.now(timezone.utc)).isoformat(),
        "updated_at": project.get("updated_at", datetime.now(timezone.utc)).isoformat(),
        "webhook_base_url": project.get("webhook_base_url", None),
    }


def token_helper(token: dict) -> dict:
    """
    Format a token document for API responses.
    Never exposes the full token — only prefix + suffix (masked).
    """
    return {
        "id": str(token["_id"]),
        "project_id": token.get("project_id", ""),
        "label": token.get("label", ""),
        "token_masked": f"{token.get('token_prefix', '')}...{token.get('token_suffix', '')}",
        "is_active": token.get("is_active", True),
        "created_at": token.get("created_at", datetime.now(timezone.utc)).isoformat(),
        "last_used_at": (
            token["last_used_at"].isoformat() if token.get("last_used_at") else None
        ),
    }
