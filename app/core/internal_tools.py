"""
Internal tools: LLM-callable tools that operate directly on the application's DB.

Currently provides `manage_tasks` for creating/listing/deleting/toggling scheduled tasks
via natural language in chat, without requiring users to know the REST API.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.tools import tool_manager
from app.models.scheduled_task import ScheduledTask
from app.scheduler.engine import scheduler_engine
from app.scheduler.nl_parser import parse_task_description

logger = structlog.get_logger()

MANAGE_TASKS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "manage_tasks",
        "description": (
            "Create, list, delete, or toggle scheduled tasks for the user. "
            "Use this when the user wants to set up recurring automated tasks, "
            "view their existing tasks, pause/resume tasks, or remove tasks. "
            "Examples: '每天早上9点搜索AI新闻', '列出我的定时任务', '暂停/删除某个任务'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "delete", "toggle"],
                    "description": "The action to perform on scheduled tasks.",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Natural language description of the task to create. "
                        "Must include what to do and when/how often. "
                        "Required for 'create' action."
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": (
                        "UUID of the task to delete or toggle. "
                        "Required for 'delete' and 'toggle' actions."
                    ),
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for the task schedule. Defaults to Asia/Shanghai.",
                    "default": "Asia/Shanghai",
                },
            },
            "required": ["action"],
        },
    },
}

INTERNAL_TOOLS_SCHEMAS = [MANAGE_TASKS_SCHEMA]


def get_internal_tools_schemas() -> list[dict]:
    """Return all internal tool schemas in OpenAI function calling format."""
    if not settings.SCHEDULER_ENABLED:
        return []
    return INTERNAL_TOOLS_SCHEMAS


def is_internal_tool(name: str) -> bool:
    """Check if a tool name belongs to an internal tool."""
    return name in {"manage_tasks"}


async def execute_internal_tool(
    name: str, arguments: dict, user_id: uuid.UUID, db: AsyncSession
) -> str:
    """Execute an internal tool and return text result."""
    if name == "manage_tasks":
        return await _execute_manage_tasks(arguments, user_id, db)
    return f"Error: Unknown internal tool '{name}'"


async def _execute_manage_tasks(
    arguments: dict, user_id: uuid.UUID, db: AsyncSession
) -> str:
    """Execute manage_tasks actions: create, list, delete, toggle."""
    action = arguments.get("action")

    if action == "create":
        return await _action_create(arguments, user_id, db)
    elif action == "list":
        return await _action_list(user_id, db)
    elif action == "delete":
        return await _action_delete(arguments, user_id, db)
    elif action == "toggle":
        return await _action_toggle(arguments, user_id, db)
    else:
        return f"Error: Unknown action '{action}'. Use create, list, delete, or toggle."


async def _action_create(
    arguments: dict, user_id: uuid.UUID, db: AsyncSession
) -> str:
    """Create a scheduled task from natural language description."""
    description = arguments.get("description")
    if not description:
        return "Error: 'description' is required for create action."

    timezone = arguments.get("timezone", "Asia/Shanghai")

    # Get available tool names for the NL parser
    available_tools = None
    if tool_manager.has_tools:
        available_tools = [t["function"]["name"] for t in tool_manager.get_tools_schema()]

    try:
        parsed = await parse_task_description(
            description, timezone=timezone, available_tools=available_tools
        )
    except (ValueError, Exception) as e:
        logger.warning("internal_tools.create_parse_failed", error=str(e))
        return f"Error parsing task description: {e}"

    cron_expression = parsed["cron_expression"]
    name = parsed["name"]
    task_config = {
        "prompt": parsed["prompt"],
        "tools": parsed.get("tools", []),
        "model": parsed.get("model", settings.DEFAULT_MODEL),
    }

    # Validate cron
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(cron_expression)
    except (ValueError, KeyError) as e:
        return f"Error: Invalid cron expression '{cron_expression}': {e}"

    task = ScheduledTask(
        user_id=user_id,
        name=name,
        description=description,
        cron_expression=cron_expression,
        timezone=timezone,
        task_config=task_config,
    )
    db.add(task)
    await db.flush()

    # Register with scheduler
    scheduler_engine.add_task(task.id, cron_expression, timezone)
    next_run = scheduler_engine.get_next_run_time(task.id)
    if next_run:
        task.next_run_at = next_run
        await db.flush()

    next_run_str = next_run.strftime("%Y-%m-%d %H:%M %Z") if next_run else "unknown"
    logger.info(
        "internal_tools.task_created",
        task_id=str(task.id),
        name=name,
        cron=cron_expression,
    )

    return (
        f"Task created successfully.\n"
        f"- ID: {task.id}\n"
        f"- Name: {name}\n"
        f"- Schedule: {cron_expression} ({timezone})\n"
        f"- Next run: {next_run_str}\n"
        f"- Prompt: {parsed['prompt'][:200]}"
    )


async def _action_list(user_id: uuid.UUID, db: AsyncSession) -> str:
    """List all scheduled tasks for the user."""
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user_id)
        .order_by(ScheduledTask.created_at.desc())
    )
    tasks = result.scalars().all()

    if not tasks:
        return "No scheduled tasks found."

    lines = [f"Found {len(tasks)} scheduled task(s):\n"]
    for i, t in enumerate(tasks, 1):
        status = "active" if t.is_active else "paused"
        next_run = ""
        if t.next_run_at:
            next_run = f", next run: {t.next_run_at.strftime('%Y-%m-%d %H:%M %Z')}"
        lines.append(
            f"{i}. [{status}] {t.name}\n"
            f"   ID: {t.id}\n"
            f"   Cron: {t.cron_expression} ({t.timezone}){next_run}"
        )

    return "\n".join(lines)


async def _action_delete(
    arguments: dict, user_id: uuid.UUID, db: AsyncSession
) -> str:
    """Delete a scheduled task."""
    task_id = arguments.get("task_id")
    if not task_id:
        return "Error: 'task_id' is required for delete action."

    task = await _get_user_task(db, task_id, user_id)
    if not task:
        return f"Error: Task '{task_id}' not found."

    name = task.name
    scheduler_engine.remove_task(task.id)
    await db.delete(task)
    await db.flush()

    logger.info("internal_tools.task_deleted", task_id=task_id, name=name)
    return f"Task '{name}' (ID: {task_id}) has been deleted."


async def _action_toggle(
    arguments: dict, user_id: uuid.UUID, db: AsyncSession
) -> str:
    """Toggle a task's active state (pause/resume)."""
    task_id = arguments.get("task_id")
    if not task_id:
        return "Error: 'task_id' is required for toggle action."

    task = await _get_user_task(db, task_id, user_id)
    if not task:
        return f"Error: Task '{task_id}' not found."

    task.is_active = not task.is_active

    if task.is_active:
        scheduler_engine.add_task(task.id, task.cron_expression, task.timezone)
        next_run = scheduler_engine.get_next_run_time(task.id)
        task.next_run_at = next_run
        next_run_str = next_run.strftime("%Y-%m-%d %H:%M %Z") if next_run else "unknown"
        status_msg = f"resumed. Next run: {next_run_str}"
    else:
        scheduler_engine.remove_task(task.id)
        task.next_run_at = None
        status_msg = "paused"

    await db.flush()

    logger.info(
        "internal_tools.task_toggled",
        task_id=task_id,
        is_active=task.is_active,
    )
    return f"Task '{task.name}' (ID: {task_id}) has been {status_msg}."


async def _get_user_task(
    db: AsyncSession, task_id: str, user_id: uuid.UUID
) -> ScheduledTask | None:
    """Fetch a task belonging to the user."""
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        return None

    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == tid,
            ScheduledTask.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
