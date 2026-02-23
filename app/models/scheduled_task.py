import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScheduledTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scheduled_tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(50))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Task execution config: {prompt, tools, model, output}
    task_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship()  # noqa: F821
    executions: Mapped[list["TaskExecution"]] = relationship(  # noqa: F821
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskExecution.created_at.desc()",
    )
