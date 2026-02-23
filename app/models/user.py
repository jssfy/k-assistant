from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
