"""
Chat Stream Service
Handles chunked HTTP chat orchestration and placeholder assistant output.
"""

from __future__ import annotations

import asyncio
import json
import time
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
    RAG_VAGUE_CONTEXT_PATH = "/api/v1/vague_context/summarize"
    RAG_CHAT_SUMMARY_PATH = "/api/v1/chat_summary"
    SUMMARY_REFRESH_INTERVAL = 10
    VAGUE_CONTEXT_RECENT_PAIRS = 4  # ~8 messages

    @staticmethod
    def _chunk_text(text: str, words_per_chunk: int) -> List[str]:
        words = text.split()
        return [
            " ".join(words[index:index + words_per_chunk])
            for index in range(0, len(words), words_per_chunk)
        ]

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

        vague_context = project.get("vague_context") or ""

        sender = {
            "type": "user",
            "id": current_user.get("id"),
            "name": current_user.get("name"),
            "email": current_user.get("email"),
        }
        staged_chat = await chat_service.stage_user_prompt(
            project_id=request.project_id,
            user_prompt=request.user_prompt,
            vague_context=vague_context,
            chat_id=request.chat_id,
            sender=sender,
            created_by=current_user.get("id"),
            created_by_name=current_user.get("name"),
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
            active_chat_id=str(staged_chat["_id"]),
        )

        # This payload is what will be sent to the LLM API.
        llm_payload = {
            "vague_context": vague_context,
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
            chat_id=str(staged_chat["_id"]),
            assistant_response=full_response,
            llm_payload={
                **llm_payload,
                "rag_metadata": rag_metadata,
            },
            simulated=False,
        )

        self._maybe_schedule_chat_summary(
            project_id=request.project_id,
            updated_chat=updated_chat,
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

    def _maybe_schedule_chat_summary(
        self,
        project_id: str,
        updated_chat: Optional[Dict[str, Any]],
    ) -> None:
        """
        Fire-and-forget: schedule a chat summary refresh if the chat has
        accumulated SUMMARY_REFRESH_INTERVAL new messages since the last summary.

        Never raises — a scheduling hiccup must not break the stream that just
        finished.
        """
        if not updated_chat:
            logger.warning(
                "summary scheduling skipped: missing updated_chat (project=%s)",
                project_id,
            )
            return

        try:
            chat_id = str(updated_chat["_id"])
            message_count = int(updated_chat.get("message_count") or 0)
            last_summarized = int(updated_chat.get("last_summarized_message_count") or 0)
            delta = message_count - last_summarized

            if delta < self.SUMMARY_REFRESH_INTERVAL:
                logger.debug(
                    "summary scheduling skipped: below threshold (chat=%s, delta=%d)",
                    chat_id,
                    delta,
                )
                return

            logger.info(
                "summary scheduling: threshold reached (chat=%s, count=%d, last_summarized=%d, delta=%d)",
                chat_id,
                message_count,
                last_summarized,
                delta,
            )
            asyncio.create_task(
                self.refresh_chat_summary(
                    project_id=project_id,
                    chat_id=chat_id,
                )
            )
        except Exception:
            logger.exception(
                "summary scheduling failed (project=%s)",
                project_id,
            )

    async def refresh_chat_summary(
        self,
        project_id: str,
        chat_id: str,
    ) -> None:
        """
        Refresh and persist a single chat's rolling summary.

        Sends only the message delta since the last summary to RAG, which
        returns a new summary that incorporates the new turns. Safe to call
        as a background task — never raises.
        """
        started = time.monotonic()
        logger.info(
            "chat_summary refresh task started (project=%s, chat=%s)",
            project_id,
            chat_id,
        )
        try:
            chat = await chat_service.get_chat(project_id, chat_id)
            if not chat:
                logger.warning(
                    "chat_summary refresh skipped: chat missing (chat=%s)",
                    chat_id,
                )
                return

            all_messages = chat_service._serialize_context_messages(chat.get("messages", []))
            if not all_messages:
                logger.info(
                    "chat_summary refresh skipped: no messages (chat=%s)",
                    chat_id,
                )
                return

            previous_summary = chat.get("chat_summary") or ""
            previous_count = int(chat.get("last_summarized_message_count") or 0)
            new_messages = all_messages[previous_count:]
            if not new_messages:
                logger.info(
                    "chat_summary refresh skipped: no new messages (chat=%s, count=%d)",
                    chat_id,
                    previous_count,
                )
                return

            url = f"{settings.RAG_SERVER_BASE_URL.rstrip('/')}{self.RAG_CHAT_SUMMARY_PATH}"
            payload = {
                "project_id": project_id,
                "chat_id": chat_id,
                "previous_summary": previous_summary,
                "new_messages": new_messages,
            }
            logger.info(
                "chat_summary RAG call (chat=%s, total=%d, delta=%d, prev_summary_len=%d)",
                chat_id,
                len(all_messages),
                len(new_messages),
                len(previous_summary),
            )

            timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    body = response.text[:500] if response.text else ""
                    logger.warning(
                        "chat_summary RAG returned %d (chat=%s, url=%s): %s",
                        response.status_code,
                        chat_id,
                        url,
                        body,
                    )
                    return
                data = response.json()

            new_summary = (data or {}).get("chat_summary")
            if not isinstance(new_summary, str) or not new_summary.strip():
                logger.warning(
                    "chat_summary RAG response missing/empty 'chat_summary' (chat=%s, response_keys=%s)",
                    chat_id,
                    list((data or {}).keys()),
                )
                return

            persisted = await chat_service.update_chat_summary(
                project_id=project_id,
                chat_id=chat_id,
                summary=new_summary,
                summarized_message_count=len(all_messages),
            )
            if not persisted:
                logger.warning(
                    "chat_summary persist skipped/failed (chat=%s)",
                    chat_id,
                )
                return

            logger.info(
                "chat_summary refreshed (chat=%s, count=%d, summary_len=%d, took=%.2fs)",
                chat_id,
                len(all_messages),
                len(new_summary),
                time.monotonic() - started,
            )
        except Exception:
            logger.exception(
                "chat_summary refresh failed (project=%s, chat=%s)",
                project_id,
                chat_id,
            )

    async def summarize_and_update_vague_context(
        self,
        project_id: str,
        actor_id: str,
        chat_id: str,
    ) -> None:
        """
        Refresh and persist the project's vague_context after a chat closes.

        Sends the chat's rolling summary plus its most recent messages to RAG.
        Safe to call as a FastAPI background task — never raises.
        """
        started = time.monotonic()
        logger.info(
            "vague_context refresh task started (project=%s, chat=%s)",
            project_id,
            chat_id,
        )
        try:
            chat = await chat_service.get_chat(project_id, chat_id)
            if not chat:
                logger.warning(
                    "vague_context skipped: chat missing (project=%s, chat=%s)",
                    project_id,
                    chat_id,
                )
                return

            chat_summary = chat.get("chat_summary") or ""
            recent_raw = chat_service._trim_recent_messages(
                chat.get("messages", []),
                max_pairs=self.VAGUE_CONTEXT_RECENT_PAIRS,
            )
            recent_messages = chat_service._serialize_context_messages(recent_raw)

            if not chat_summary and not recent_messages:
                logger.info(
                    "vague_context skipped: nothing to summarize (chat=%s)",
                    chat_id,
                )
                return

            project = await project_service.get_project(project_id, actor_id)
            if not project:
                logger.warning(
                    "vague_context skipped: project missing (project=%s)",
                    project_id,
                )
                return
            current_vague_context = project.get("vague_context") or ""

            url = f"{settings.RAG_SERVER_BASE_URL.rstrip('/')}{self.RAG_VAGUE_CONTEXT_PATH}"
            payload = {
                "project_id": project_id,
                "chat_summary": chat_summary,
                "recent_messages": recent_messages,
                "current_vague_context": current_vague_context,
            }
            logger.info(
                "vague_context RAG call (project=%s, chat=%s, summary_len=%d, recent=%d, current_len=%d)",
                project_id,
                chat_id,
                len(chat_summary),
                len(recent_messages),
                len(current_vague_context),
            )

            timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    body = response.text[:500] if response.text else ""
                    logger.warning(
                        "vague_context RAG returned %d (project=%s, url=%s): %s",
                        response.status_code,
                        project_id,
                        url,
                        body,
                    )
                    return
                data = response.json()

            new_vague_context = (data or {}).get("vague_context")
            if not isinstance(new_vague_context, str):
                logger.warning(
                    "vague_context RAG response missing 'vague_context' string (project=%s, response_keys=%s)",
                    project_id,
                    list((data or {}).keys()),
                )
                return

            persisted = await project_service.update_vague_context(
                project_id=project_id,
                user_id=actor_id,
                vague_context=new_vague_context,
            )
            if not persisted:
                logger.warning(
                    "vague_context persist returned False (project=%s)",
                    project_id,
                )
                return

            logger.info(
                "vague_context updated (project=%s, chat=%s, new_len=%d, took=%.2fs)",
                project_id,
                chat_id,
                len(new_vague_context),
                time.monotonic() - started,
            )
        except Exception:
            logger.exception(
                "vague_context refresh failed (project=%s, chat=%s)",
                project_id,
                chat_id,
            )

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
