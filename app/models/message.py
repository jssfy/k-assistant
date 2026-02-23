import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20))  # system, user, assistant
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    conversation: Mapped["Conversation"] = relationship(  # noqa: F821
        back_populates="messages"
    )
