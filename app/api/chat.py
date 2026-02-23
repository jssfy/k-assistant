import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import APIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id
from app.core.chat import chat, chat_stream
from app.core.llm import llm_client
from app.core.memory import memory_manager
from app.db.session import async_session, get_db
from app.models.conversation import Conversation
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailOut,
    ConversationOut,
    MemoryOut,
    MessageOut,
)

router = APIRouter(prefix="/api")


logger = structlog.get_logger()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        conversation, assistant_msg = await chat(
            db, user_id, req.message, req.conversation_id, req.model
        )
    except APIError as e:
        logger.error("chat.llm_error", status=e.status_code, message=str(e))
        raise HTTPException(status_code=502, detail=f"LLM service error: {e.message}")
    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageOut.model_validate(assistant_msg),
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    req: ChatRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async def generate():
        async with async_session() as db:
            try:
                async for event in chat_stream(
                    db, user_id, req.message, req.conversation_id, req.model
                ):
                    yield event
            except Exception:
                await db.rollback()
                raise

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)


@router.get("/models")
async def list_models():
    models = await llm_client.list_models()
    return {"models": models}


# === Memory endpoints ===


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    if not memory_manager.enabled:
        return []
    memories = await memory_manager.list(str(user_id))
    return [_mem_to_out(m) for m in memories]


@router.get("/memories/search", response_model=list[MemoryOut])
async def search_memories(
    q: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    if not memory_manager.enabled:
        return []
    memories = await memory_manager.search(str(user_id), q)
    return [_mem_to_out(m) for m in memories]


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    if not memory_manager.enabled:
        raise HTTPException(status_code=503, detail="Memory system not enabled")
    success = await memory_manager.delete(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")


def _mem_to_out(m: dict) -> MemoryOut:
    return MemoryOut(
        id=m.get("id", ""),
        memory=m.get("memory", ""),
        metadata=m.get("metadata"),
        created_at=m.get("created_at"),
        updated_at=m.get("updated_at"),
    )
