"""
Chat Schemas
Pydantic schemas for chat request/response payloads.
"""

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, Field


class ChatStreamRequest(BaseModel):
    """HTTP request body for a streamed chat response."""

    project_id: str = Field(
        ...,
        validation_alias=AliasChoices("projectId", "project_id"),
    )
    chat_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("chatId", "chat_id"),
    )
    vague_context: str = Field(
        default="",
        validation_alias=AliasChoices(
            "vagueContext",
            "vague_context",
            "vauge_context",
            "vaugeContext",
        ),
    )
    user_prompt: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("userPrompt", "user_prompt"),
    )


class ChatContextMessageResponse(BaseModel):
    """Single LLM-friendly chat context message."""

    role: str
    content: str


class ChatSummaryResponse(BaseModel):
    """Chat summary shown in the project chat list."""

    id: str
    project_id: str
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    title: str
    message_count: int
    created_at: str
    updated_at: str


class ProjectChatListData(BaseModel):
    """Payload for listing chats under a project."""

    project_id: str
    project_name: str
    chats: List[ChatSummaryResponse]


class ChatContextResponse(BaseModel):
    """Payload for a single chat context."""

    chat_context: List[ChatContextMessageResponse]
