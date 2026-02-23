import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    """Create a task - either via natural language or explicit config."""
    name: str | None = None
    description: str  # Natural language description OR explicit instructions
    cron_expression: str | None = None  # If None, LLM will parse from description
    timezone: str = "Asia/Shanghai"
    task_config: dict | None = None  # Override auto-parsed config if provided
    model: str | None = None


class TaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    is_active: bool | None = None
    task_config: dict | None = None


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None = None
    cron_expression: str
    timezone: str
    is_active: bool
    task_config: dict
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskExecutionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    task_id: uuid.UUID
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    token_usage: int | None = None
    created_at: datetime
