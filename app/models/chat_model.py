"""
Chat Models
Defines chat document structures and response helpers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatMessageModel(BaseModel):
    """Single message inside a chat transcript."""

    role: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "Why did the deployment fail?",
                "created_at": "2026-04-27T12:30:00Z",
                "metadata": {"source": "dashboard"},
            }
        }


class ChatModel(BaseModel):
    """MongoDB chat document."""

    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    owner_id: Optional[str] = None
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    title: str
    encrypted_payload: str
    message_count: int = 0
    chat_summary: Optional[str] = None
    last_summarized_at: Optional[datetime] = None
    last_summarized_message_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "project_id": "680e3eb793b2f0d6032f45ab",
                "created_by": "680e3e8f93b2f0d6032f45aa",
                "created_by_name": "Ada Lovelace",
                "title": "Root cause analysis",
                "encrypted_payload": "<fernet-token>",
                "message_count": 8,
            }
        }


def chat_summary_helper(chat: dict) -> dict:
    """Format a chat summary document for API responses."""
    last_summarized_at = chat.get("last_summarized_at")
    return {
        "id": str(chat["_id"]),
        "project_id": chat.get("project_id", ""),
        "created_by": chat.get("created_by") or chat.get("owner_id"),
        "created_by_name": chat.get("created_by_name"),
        "title": chat.get("title", ""),
        "message_count": chat.get("message_count", 0),
        "chat_summary": chat.get("chat_summary") or "",
        "last_summarized_at": (
            last_summarized_at.isoformat() if last_summarized_at else None
        ),
        "last_summarized_message_count": chat.get("last_summarized_message_count", 0),
        "created_at": chat.get("created_at", datetime.now(timezone.utc)).isoformat(),
        "updated_at": chat.get("updated_at", datetime.now(timezone.utc)).isoformat(),
    }


def chat_detail_helper(chat: dict, messages: List[dict]) -> dict:
    """Format a full chat document for API responses."""
    payload = chat_summary_helper(chat)
    payload["messages"] = messages
    return payload
