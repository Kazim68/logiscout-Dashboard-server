"""
Project & Token Schemas
Pydantic schemas for request/response validation.
"""

from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ============================================
# Project Schemas
# ============================================

class ProjectCreateRequest(BaseModel):
    """Schema for creating a new project."""
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: Optional[str] = Field(None, max_length=500, description="Project description")
    language: str = Field("python", pattern="^(python|nodejs)$", description="Project language: python or nodejs")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Payment Service",
                "description": "Handles all payment processing and billing logic",
                "language": "python",
            }
        }


class ProjectUpdateRequest(BaseModel):
    """Schema for updating a project."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")
    webhook_base_url: Optional[str] = Field(None, max_length=500)


class ProjectResponse(BaseModel):
    """Schema for a single project in responses."""
    id: str
    name: str
    description: Optional[str] = None
    language: str = "python"
    owner_id: str
    status: str
    created_at: str
    updated_at: str
    token_count: Optional[int] = 0
    webhook_base_url: Optional[str] = None
    vague_context: Optional[str] = None


class ProjectListResponse(BaseModel):
    """Schema for project list responses."""
    success: bool
    message: str
    data: List[ProjectResponse]


# ============================================
# Token Schemas
# ============================================

class TokenCreateRequest(BaseModel):
    """Schema for creating a new API token."""
    label: str = Field(
        default="Default",
        min_length=1,
        max_length=50,
        description="Human-friendly label (e.g. Production, Staging)",
    )

    class Config:
        json_schema_extra = {"example": {"label": "Production"}}


class TokenResponse(BaseModel):
    """Schema for a token in list responses (masked)."""
    id: str
    project_id: str
    label: str
    token_masked: str
    is_active: bool = True
    created_at: str
    last_used_at: Optional[str] = None


class TokenCreatedResponse(BaseModel):
    """
    Schema returned only at token creation.
    Contains the FULL plain-text token — shown once, never again.
    """
    id: str
    project_id: str
    label: str
    token: str  # Full plain-text token (shown ONLY at creation)
    token_masked: str
    is_active: bool = True
    created_at: str


# ============================================
# Collaborator Schemas
# ============================================

class CollaboratorInviteRequest(BaseModel):
    """Schema for inviting a collaborator by email."""
    email: EmailStr = Field(..., description="Email of an existing LogiScout user")
    role: str = Field("read", pattern="^(read|edit)$", description="Access level: read or edit")

    class Config:
        json_schema_extra = {
            "example": {"email": "teammate@example.com", "role": "edit"}
        }


class CollaboratorUpdateRequest(BaseModel):
    """Schema for changing a collaborator's role."""
    role: str = Field(..., pattern="^(read|edit)$", description="New access level: read or edit")


class CollaboratorAcceptRequest(BaseModel):
    """Schema for accepting a collaborator invite."""
    invite_token: str = Field(..., min_length=10, description="Unique invite token from email link")


class CollaboratorResponse(BaseModel):
    """Schema for a collaborator in API responses."""
    id: str
    project_id: str
    user_id: str
    email: str
    name: str
    role: str        # "read" | "edit"
    status: str      # "pending" | "active"
    created_at: str
    accepted_at: Optional[str] = None
