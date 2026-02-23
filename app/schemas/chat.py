import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None
    model: str | None = None


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    role: str
    content: str
    model: str | None = None
    token_usage: int | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str | None = None
    model: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut


class MemoryOut(BaseModel):
    id: str
    memory: str
    metadata: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
