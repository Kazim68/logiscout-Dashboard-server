"""
Project Model
Defines the Project and API Token document structures for MongoDB.
"""

from datetime import datetime
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

    Tokens are stored as SHA-256 hashes. The plain-text token is only
    returned at creation time.

    Attributes:
        id: MongoDB ObjectId
        project_id: Parent project ID
        owner_id: User ID who owns this token
        label: Human-friendly label (e.g. "Production", "Staging")
        token_hash: SHA-256 hash of the full token
        token_prefix: First 8 chars for display (e.g. "lgs_kx92")
        token_suffix: Last 4 chars for display
        created_at: Creation timestamp
        last_used_at: Last usage timestamp (updated on log ingestion)
    """

    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    owner_id: str
    label: str = "Default"
    token_hash: str
    token_prefix: str  # e.g. "lgs_kx92"
    token_suffix: str  # e.g. "r8t"
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
        "created_at": project.get("created_at", datetime.utcnow()).isoformat(),
        "updated_at": project.get("updated_at", datetime.utcnow()).isoformat(),
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
        "created_at": token.get("created_at", datetime.utcnow()).isoformat(),
        "last_used_at": token.get("last_used_at").isoformat() if token.get("last_used_at") else None,
    }
