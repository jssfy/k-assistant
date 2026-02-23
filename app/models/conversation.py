import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversations"

    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )

    user: Mapped["User"] = relationship(back_populates="conversations")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
