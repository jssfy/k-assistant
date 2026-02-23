import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id
from app.core.chat import chat, chat_stream
from app.core.llm import llm_client
from app.db.session import get_db
from app.models.conversation import Conversation
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailOut,
    ConversationOut,
    MessageOut,
)

router = APIRouter(prefix="/api")


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    conversation, assistant_msg = await chat(
        db, user_id, req.message, req.conversation_id, req.model
    )
    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageOut.model_validate(assistant_msg),
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return StreamingResponse(
        chat_stream(db, user_id, req.message, req.conversation_id, req.model),
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
