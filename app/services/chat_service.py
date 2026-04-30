"""
Chat Service
Business logic for encrypted chat storage and retrieval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.core import database as db
from app.core.chat_encryption import chat_encryption
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ChatService:
    """Handles encrypted project chat storage and retrieval."""

    _indexes_ready = False

    @classmethod
    async def ensure_indexes(cls) -> None:
        """Create indexes needed for chat lookups once per process."""
        if cls._indexes_ready:
            return

        try:
            await db.Chats.create_index(
                [("owner_id", 1), ("project_id", 1), ("updated_at", -1)],
                name="owner_project_updated_at_idx",
            )
            await db.Chats.create_index(
                [("project_id", 1), ("created_at", -1)],
                name="project_created_at_idx",
            )
            cls._indexes_ready = True
            logger.info("Ensured chat collection indexes")
        except Exception as exc:
            logger.warning("Unable to ensure chat indexes: %s", exc)

    @staticmethod
    def _normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_messages: List[Dict[str, Any]] = []

        for raw_message in messages:
            if not isinstance(raw_message, dict):
                raise ValueError("Each chat message must be an object")

            role = str(raw_message.get("role", "")).strip()
            content = str(raw_message.get("content", "")).strip()
            created_at = raw_message.get("created_at")
            metadata = raw_message.get("metadata") or {}

            if not role:
                raise ValueError("Each chat message must include a role")
            if not content:
                raise ValueError("Each chat message must include content")
            if not isinstance(metadata, dict):
                raise ValueError("Chat message metadata must be an object")

            if hasattr(created_at, "isoformat"):
                created_at_value = created_at.isoformat()
            elif created_at:
                created_at_value = str(created_at)
            else:
                created_at_value = datetime.now(timezone.utc).isoformat()

            normalized_messages.append(
                {
                    "role": role,
                    "content": content,
                    "created_at": created_at_value,
                    "metadata": metadata,
                }
            )

        return normalized_messages

    @staticmethod
    def _build_message(
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "role": role.strip(),
            "content": content.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

    @staticmethod
    def _derive_title(user_prompt: str) -> str:
        title = " ".join(user_prompt.strip().split())
        return title[:60] if len(title) <= 60 else f"{title[:57]}..."

    @staticmethod
    def _trim_recent_messages(
        messages: List[Dict[str, Any]],
        max_pairs: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Return the most recent user/assistant turns in chronological order.

        `max_pairs=4` means up to 8 messages when the sequence is clean
        user/assistant alternation.
        """
        chat_messages = [
            message
            for message in messages
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]
        return chat_messages[-(max_pairs * 2):]

    @staticmethod
    def _serialize_context_messages(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """Reduce context messages to the minimal LLM-friendly shape."""
        return [
            {
                "role": str(message.get("role", "")).strip(),
                "content": str(message.get("content", "")).strip(),
            }
            for message in messages
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]

    @staticmethod
    def _drop_incomplete_trailing_turns(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Drop trailing user-only turns that do not yet have an assistant reply.
        """
        normalized_messages = list(messages)
        while normalized_messages and normalized_messages[-1].get("role") == "user":
            normalized_messages = normalized_messages[:-1]
        return normalized_messages

    async def get_chat_context(
        self,
        project_id: str,
        chat_id: str,
        owner_id: str,
        max_pairs: Optional[int] = None,
        drop_incomplete_trailing_turns: bool = False,
    ) -> List[Dict[str, str]]:
        """
        Return a minimal chat context with only role/content pairs.

        This is the only shape that should be sent to the LLM.
        """
        chat = await self.get_chat(project_id, chat_id, owner_id)
        if not chat:
            return []

        context_messages = chat.get("messages", [])
        if drop_incomplete_trailing_turns:
            context_messages = self._drop_incomplete_trailing_turns(context_messages)

        if max_pairs is not None:
            context_messages = self._trim_recent_messages(
                context_messages,
                max_pairs=max_pairs,
            )

        return self._serialize_context_messages(context_messages)

    async def create_chat(
        self,
        project_id: str,
        owner_id: str,
        title: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a new encrypted chat document."""
        if not title or not title.strip():
            raise ValueError("Chat title is required")

        await self.ensure_indexes()

        normalized_messages = self._normalize_messages(messages)
        now = datetime.now(timezone.utc)

        doc = {
            "project_id": project_id,
            "owner_id": owner_id,
            "title": title.strip(),
            "encrypted_payload": chat_encryption.encrypt_payload(
                {"messages": normalized_messages}
            ),
            "message_count": len(normalized_messages),
            "created_at": now,
            "updated_at": now,
        }

        result = await db.Chats.insert_one(doc)
        created = await db.Chats.find_one({"_id": result.inserted_id})
        logger.info(
            "Chat created for project %s",
            project_id,
            extra={"project_id": project_id, "chat_id": str(result.inserted_id)},
        )
        return created

    async def stage_user_prompt(
        self,
        project_id: str,
        owner_id: str,
        user_prompt: str,
        vague_context: str = "",
        chat_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create or update a chat with the incoming user prompt before streaming."""
        prompt_message = self._build_message(
            role="user",
            content=user_prompt,
            metadata={"vague_context": vague_context} if vague_context else {},
        )

        if chat_id:
            existing_chat = await self.get_chat(project_id, chat_id, owner_id)
            if not existing_chat:
                return None

            updated_messages = existing_chat.get("messages", []) + [prompt_message]
            return await self.replace_chat_messages(
                project_id=project_id,
                chat_id=chat_id,
                owner_id=owner_id,
                messages=updated_messages,
            )

        return await self.create_chat(
            project_id=project_id,
            owner_id=owner_id,
            title=self._derive_title(user_prompt),
            messages=[prompt_message],
        )

    async def finalize_assistant_response(
        self,
        project_id: str,
        owner_id: str,
        chat_id: str,
        assistant_response: str,
        llm_payload: Optional[Dict[str, Any]] = None,
        simulated: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Append the assistant response after streaming completes."""
        existing_chat = await self.get_chat(project_id, chat_id, owner_id)
        if not existing_chat:
            return None

        updated_messages = existing_chat.get("messages", []) + [
            self._build_message(
                role="assistant",
                content=assistant_response,
                metadata={
                    "simulated": simulated,
                    "llm_payload": llm_payload or {},
                },
            )
        ]
        return await self.replace_chat_messages(
            project_id=project_id,
            chat_id=chat_id,
            owner_id=owner_id,
            messages=updated_messages,
        )

    async def replace_chat_messages(
        self,
        project_id: str,
        chat_id: str,
        owner_id: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Replace the full encrypted chat payload for an existing chat."""
        await self.ensure_indexes()
        normalized_messages = self._normalize_messages(messages)

        update_data: Dict[str, Any] = {
            "encrypted_payload": chat_encryption.encrypt_payload(
                {"messages": normalized_messages}
            ),
            "message_count": len(normalized_messages),
            "updated_at": datetime.now(timezone.utc),
        }
        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValueError("Chat title cannot be empty")
            update_data["title"] = clean_title

        try:
            result = await db.Chats.find_one_and_update(
                {
                    "_id": ObjectId(chat_id),
                    "project_id": project_id,
                    "owner_id": owner_id,
                },
                {"$set": update_data},
                return_document=ReturnDocument.AFTER,
            )
            return result
        except Exception:
            logger.warning("replace_chat_messages failed: chat_id=%s", chat_id)
            return None

    async def list_project_chats(
        self,
        project_id: str,
        owner_id: str,
    ) -> List[Dict[str, Any]]:
        """List all chat summaries for a project."""
        await self.ensure_indexes()
        cursor = db.Chats.find(
            {"project_id": project_id, "owner_id": owner_id},
            {
                "project_id": 1,
                "title": 1,
                "message_count": 1,
                "created_at": 1,
                "updated_at": 1,
            },
        ).sort("updated_at", -1)
        return await cursor.to_list(length=500)

    async def get_recent_chat_context(
        self,
        project_id: str,
        owner_id: str,
        active_chat_id: Optional[str] = None,
        max_pairs: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Return the previous 3-4 question/answer turns for the LLM payload.

        Priority:
        1. Earlier messages from the active chat, excluding the just-submitted prompt
        2. Most recent messages from older chats in the same project as fallback
        """
        context_messages: List[Dict[str, Any]] = []
        max_messages = max_pairs * 2

        if active_chat_id:
            context_messages.extend(
                await self.get_chat_context(
                    project_id=project_id,
                    chat_id=active_chat_id,
                    owner_id=owner_id,
                    max_pairs=max_pairs,
                    drop_incomplete_trailing_turns=True,
                )
            )

        if len(context_messages) >= max_messages:
            return context_messages[-max_messages:]

        chat_docs = await self.list_project_chats(project_id, owner_id)
        for chat_doc in chat_docs:
            chat_id = str(chat_doc["_id"])
            if active_chat_id and chat_id == active_chat_id:
                continue

            fallback_messages = await self.get_chat_context(
                project_id=project_id,
                chat_id=chat_id,
                owner_id=owner_id,
                max_pairs=max_pairs,
                drop_incomplete_trailing_turns=True,
            )
            if not fallback_messages:
                continue

            remaining = max_messages - len(context_messages)
            context_messages = fallback_messages[-remaining:] + context_messages

            if len(context_messages) >= max_messages:
                break

        return context_messages[-max_messages:]

    async def get_chat(
        self,
        project_id: str,
        chat_id: str,
        owner_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load and decrypt a full chat."""
        try:
            chat = await db.Chats.find_one(
                {
                    "_id": ObjectId(chat_id),
                    "project_id": project_id,
                    "owner_id": owner_id,
                }
            )
        except Exception:
            logger.warning("get_chat failed: chat_id=%s", chat_id)
            return None

        if not chat:
            return None

        payload = chat_encryption.decrypt_payload(chat["encrypted_payload"])
        chat["messages"] = payload.get("messages", [])
        return chat


chat_service = ChatService()
