import json
import uuid
from collections.abc import AsyncIterator

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.llm import llm_client
from app.models.conversation import Conversation
from app.models.message import Message

logger = structlog.get_logger()

SYSTEM_PROMPT = "You are a helpful personal AI assistant. Be concise and clear in your responses."


async def get_or_create_conversation(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    model: str | None = None,
) -> Conversation:
    if conversation_id:
        result = await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(
        user_id=user_id,
        model=model or settings.DEFAULT_MODEL,
    )
    db.add(conv)
    await db.flush()
    return conv


def build_messages(conversation: Conversation, new_message: str) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation.messages:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": new_message})
    return messages


async def _set_title(db: AsyncSession, conversation: Conversation, first_message: str):
    title = first_message[:80].split("\n")[0]
    if len(first_message) > 80:
        title += "..."
    conversation.title = title
    await db.flush()


async def chat(
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    conversation_id: uuid.UUID | None = None,
    model: str | None = None,
) -> tuple[Conversation, Message]:
    """Non-streaming chat. Returns (conversation, assistant_message)."""
    conversation = await get_or_create_conversation(db, user_id, conversation_id, model)
    messages = build_messages(conversation, message)

    # Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    # Set title from first message
    if not conversation.title:
        await _set_title(db, conversation, message)

    # Call LLM
    content, usage = await llm_client.complete(messages, conversation.model)

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        model=conversation.model,
        token_usage=usage.get("total_tokens"),
    )
    db.add(assistant_msg)
    await db.flush()

    return conversation, assistant_msg


async def chat_stream(
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    conversation_id: uuid.UUID | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Streaming chat. Yields SSE events."""
    conversation = await get_or_create_conversation(db, user_id, conversation_id, model)
    messages = build_messages(conversation, message)

    # Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    # Set title from first message
    if not conversation.title:
        await _set_title(db, conversation, message)

    # Stream metadata
    yield _sse_event("metadata", {
        "conversation_id": str(conversation.id),
        "model": conversation.model,
    })

    # Stream LLM response
    full_content = ""
    try:
        async for delta in llm_client.stream(messages, conversation.model):
            full_content += delta
            yield _sse_event("message", {"content": delta})
    except Exception as e:
        logger.exception("chat_stream.error")
        yield _sse_event("error", {"message": str(e)})
        return

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=full_content,
        model=conversation.model,
    )
    db.add(assistant_msg)
    await db.flush()
    await db.commit()

    yield _sse_event("done", {"message_id": str(assistant_msg.id)})


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
