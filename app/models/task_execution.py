import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class TaskExecution(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "task_executions"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduled_tasks.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/success/failed
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Execution details
    llm_messages: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_calls_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["ScheduledTask"] = relationship(back_populates="executions")  # noqa: F821
