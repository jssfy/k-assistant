import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id
from app.core.tools import tool_manager
from app.db.session import get_db
from app.models.scheduled_task import ScheduledTask
from app.models.task_execution import TaskExecution
from app.scheduler.engine import scheduler_engine
from app.scheduler.nl_parser import parse_task_description
from app.schemas.task import TaskCreate, TaskExecutionOut, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = structlog.get_logger()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    req: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Create a scheduled task. Supports natural language or explicit cron."""
    cron_expression = req.cron_expression
    task_config = req.task_config or {}
    name = req.name

    # If no cron provided, use LLM to parse from description
    if not cron_expression:
        available_tools = None
        if tool_manager.has_tools:
            available_tools = [t["function"]["name"] for t in tool_manager.get_tools_schema()]

        try:
            parsed = await parse_task_description(
                req.description,
                timezone=req.timezone,
                available_tools=available_tools,
            )
        except (ValueError, Exception) as e:
            raise HTTPException(status_code=422, detail=str(e))

        cron_expression = parsed["cron_expression"]
        name = name or parsed["name"]
        task_config = {
            "prompt": parsed["prompt"],
            "tools": parsed.get("tools", []),
            "model": parsed.get("model", req.model),
        }
    else:
        # Explicit cron - build config from request
        if not task_config:
            task_config = {
                "prompt": req.description,
                "tools": [],
                "model": req.model,
            }
        name = name or req.description[:80]

    # Validate cron expression
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(cron_expression)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {e}")

    task = ScheduledTask(
        user_id=user_id,
        name=name,
        description=req.description,
        cron_expression=cron_expression,
        timezone=req.timezone,
        task_config=task_config,
    )
    db.add(task)
    await db.flush()

    # Register with scheduler
    scheduler_engine.add_task(task.id, cron_expression, req.timezone)
    next_run = scheduler_engine.get_next_run_time(task.id)
    if next_run:
        task.next_run_at = next_run
        await db.flush()

    await db.refresh(task)
    logger.info("api.task_created", task_id=str(task.id), name=name, cron=cron_expression)
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """List all scheduled tasks for the current user."""
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user_id)
        .order_by(ScheduledTask.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    task = await _get_user_task(db, task_id, user_id)
    return task


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    req: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Update a scheduled task."""
    task = await _get_user_task(db, task_id, user_id)

    if req.name is not None:
        task.name = req.name
    if req.description is not None:
        task.description = req.description
    if req.timezone is not None:
        task.timezone = req.timezone
    if req.task_config is not None:
        task.task_config = req.task_config
    if req.is_active is not None:
        task.is_active = req.is_active
        if req.is_active:
            scheduler_engine.add_task(task.id, task.cron_expression, task.timezone)
        else:
            scheduler_engine.remove_task(task.id)

    if req.cron_expression is not None:
        # Validate
        try:
            from apscheduler.triggers.cron import CronTrigger
            CronTrigger.from_crontab(req.cron_expression)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid cron expression: {e}")
        task.cron_expression = req.cron_expression
        if task.is_active:
            scheduler_engine.update_task(task.id, req.cron_expression, task.timezone)

    # Update next_run_at
    next_run = scheduler_engine.get_next_run_time(task.id)
    task.next_run_at = next_run

    await db.flush()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Delete a scheduled task."""
    task = await _get_user_task(db, task_id, user_id)
    scheduler_engine.remove_task(task.id)
    await db.delete(task)


@router.post("/{task_id}/run", response_model=TaskExecutionOut)
async def trigger_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """Manually trigger a task execution."""
    task = await _get_user_task(db, task_id, user_id)

    # Run task directly (not through scheduler)
    from app.scheduler.task_runner import run_task
    await run_task(str(task.id))

    # Fetch the latest execution
    result = await db.execute(
        select(TaskExecution)
        .where(TaskExecution.task_id == task.id)
        .order_by(TaskExecution.created_at.desc())
        .limit(1)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=500, detail="Task execution not recorded")
    return execution


@router.get("/{task_id}/executions", response_model=list[TaskExecutionOut])
async def list_executions(
    task_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """List execution history for a task."""
    await _get_user_task(db, task_id, user_id)  # Authorization check

    result = await db.execute(
        select(TaskExecution)
        .where(TaskExecution.task_id == task_id)
        .order_by(TaskExecution.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def _get_user_task(db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID) -> ScheduledTask:
    """Fetch a task that belongs to the user, or raise 404."""
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.user_id == user_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
