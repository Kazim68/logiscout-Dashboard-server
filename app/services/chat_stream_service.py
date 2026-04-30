"""
Chat Stream Service
Handles chunked HTTP chat orchestration and placeholder assistant output.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.core.config import settings
from app.schemas.chat_schema import ChatStreamRequest
from app.core.logging_config import get_logger
from app.services.chat_service import chat_service
from app.services.project_service import project_service

logger = get_logger(__name__)


class ChatStreamService:
    """Coordinates context loading, streaming, and chat persistence."""

    CHUNK_DELAY_SECONDS = 0.06
    CHUNK_WORDS = 3
    RAG_RESPONSE_PATH = "/api/v1/response"

    @staticmethod
    def _chunk_text(text: str, words_per_chunk: int) -> List[str]:
        words = text.split()
        return [
            " ".join(words[index:index + words_per_chunk])
            for index in range(0, len(words), words_per_chunk)
        ]

    @staticmethod
    def get_vauge_context() -> str:
        """
        Return the vague context exactly as supplied by the client.

        The spelling is kept to match the existing API contract.
        """
        return 

    @staticmethod
    def _build_rag_request_payload(llm_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "vague_context": llm_payload.get("vague_context"),
            "chat_context": llm_payload.get("chat_context"),
            "user_prompt": llm_payload.get("user_prompt", ""),
            "project_id": llm_payload.get("projectId", ""),
        }

    async def _stream_rag_response(
        self,
        llm_payload: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        rag_url = f"{settings.RAG_SERVER_BASE_URL.rstrip('/')}{self.RAG_RESPONSE_PATH}"
        request_payload = self._build_rag_request_payload(llm_payload)

        timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream("POST", rag_url, json=request_payload) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise RuntimeError(
                            f"RAG API returned {response.status_code}: {body.decode('utf-8', errors='ignore')[:500]}"
                        )

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise RuntimeError(f"Invalid NDJSON chunk from RAG API: {line[:200]}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"RAG API request failed: {exc}") from exc

    async def iter_stream_events(
        self,
        current_user: dict,
        request: ChatStreamRequest,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Yield normalized chat stream events for HTTP transport."""
        project = await project_service.get_project(request.project_id, current_user["id"])
        if not project:
            yield {
                "type": "error",
                "message": "Project not found",
                "projectId": request.project_id,
            }
            return

        staged_chat = await chat_service.stage_user_prompt(
            project_id=request.project_id,
            owner_id=current_user["id"],
            user_prompt=request.user_prompt,
            vague_context=self.get_vauge_context(),
            chat_id=request.chat_id,
        )
        if not staged_chat:
            yield {
                "type": "error",
                "message": "Chat not found",
                "projectId": request.project_id,
                "chatId": request.chat_id,
            }
            return

        chat_context = await chat_service.get_recent_chat_context(
            project_id=request.project_id,
            owner_id=current_user["id"],
            active_chat_id=str(staged_chat["_id"]),
        )

        # This payload is what will be sent to the LLM API.
        llm_payload = {
            "vague_context": self.get_vauge_context(),
            "chat_context": chat_context,
            "projectId": request.project_id,
            "user_prompt": request.user_prompt,
        }
        
        
        # logger.info("Chat context: %s", chat_context)

        yield {
            "type": "context_ready",
            "projectId": request.project_id,
            "chatId": str(staged_chat["_id"]),
            "payload": llm_payload,
        }

        assistant_message_id = uuid.uuid4().hex
        yield {
            "type": "assistant_start",
            "projectId": request.project_id,
            "chatId": str(staged_chat["_id"]),
            "messageId": assistant_message_id,
        }

        collected_chunks: List[str] = []
        rag_metadata: Dict[str, Any] = {
            "provider": None,
            "warning": None,
            "sources": [],
            "intent": None,
        }

        async for rag_event in self._stream_rag_response(llm_payload):
            event_name = rag_event.get("event")
            event_data = rag_event.get("data") or {}

            if event_name == "status":
                yield {
                    "type": "pipeline_status",
                    "projectId": request.project_id,
                    "chatId": str(staged_chat["_id"]),
                    "stage": event_data.get("stage"),
                    "data": event_data,
                }
                continue

            if event_name == "intent":
                rag_metadata["intent"] = event_data
                yield {
                    "type": "pipeline_intent",
                    "projectId": request.project_id,
                    "chatId": str(staged_chat["_id"]),
                    "data": event_data,
                }
                continue

            if event_name == "error":
                raise RuntimeError(event_data.get("message") or "RAG pipeline returned an error")

            if event_name == "answer":
                rag_metadata["provider"] = event_data.get("provider")
                rag_metadata["warning"] = event_data.get("warning")
                answer_text = str(event_data.get("text") or "").strip()

                if not answer_text:
                    raise RuntimeError("RAG pipeline returned an empty answer")

                for chunk in self._chunk_text(answer_text, self.CHUNK_WORDS):
                    chunk_text = f"{chunk} "
                    collected_chunks.append(chunk_text)
                    yield {
                        "type": "assistant_delta",
                        "projectId": request.project_id,
                        "chatId": str(staged_chat["_id"]),
                        "messageId": assistant_message_id,
                        "delta": chunk_text,
                    }
                    await asyncio.sleep(self.CHUNK_DELAY_SECONDS)
                continue

            if event_name == "done":
                rag_metadata["sources"] = event_data.get("sources") or []
                break

        full_response = "".join(collected_chunks).strip()
        if not full_response:
            raise RuntimeError("RAG pipeline completed without producing an answer")

        updated_chat = await chat_service.finalize_assistant_response(
            project_id=request.project_id,
            owner_id=current_user["id"],
            chat_id=str(staged_chat["_id"]),
            assistant_response=full_response,
            llm_payload={
                **llm_payload,
                "rag_metadata": rag_metadata,
            },
            simulated=False,
        )

        yield {
            "type": "assistant_done",
            "projectId": request.project_id,
            "chatId": str(updated_chat["_id"]) if updated_chat else str(staged_chat["_id"]),
            "messageId": assistant_message_id,
            "content": full_response,
            "provider": rag_metadata.get("provider"),
            "sources": rag_metadata.get("sources") or [],
            "warning": rag_metadata.get("warning"),
        }

    async def iter_sse_chunks(
        self,
        current_user: dict,
        request: ChatStreamRequest,
    ) -> AsyncIterator[str]:
        """Yield SSE-formatted chunks for HTTP streaming."""
        try:
            async for payload in self.iter_stream_events(
                current_user=current_user,
                request=request,
            ):
                event_type = payload.get("type", "message")
                yield f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
        except Exception as exc:
            logger.exception(
                "HTTP chat stream failed",
                extra={"user_id": current_user.get("id"), "project_id": request.project_id},
            )
            error_payload = {
                "type": "error",
                "message": str(exc),
                "projectId": request.project_id,
            }
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=True)}\n\n"


chat_stream_service = ChatStreamService()
