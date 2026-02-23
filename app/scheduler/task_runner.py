"""
Task runner: executes scheduled tasks when triggered by APScheduler.

Flow:
1. Load task_config from DB
2. Retrieve relevant memories
3. Build prompt with context
4. Call LLM (with tool execution loop)
5. Record execution log
"""

import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from app.config import settings
from app.core.llm import LLMResponse, llm_client
from app.core.memory import memory_manager
from app.core.tools import tool_manager
from app.db.session import async_session
from app.models.scheduled_task import ScheduledTask
from app.models.task_execution import TaskExecution

logger = structlog.get_logger()

TASK_SYSTEM_PROMPT = (
    "You are an AI assistant executing a scheduled task. "
    "Complete the task according to the instructions below. "
    "Be thorough and provide a well-structured result."
)

MAX_TOOL_ROUNDS = 10


async def run_task(task_id: str):
    """
    Execute a scheduled task. Called by APScheduler.

    This runs in a standalone context (no HTTP request), so we manage our own DB session.
    """
    log = logger.bind(task_id=task_id)
    log.info("task_runner.start")

    async with async_session() as db:
        # Load task from DB
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(task_id))
        )
        task = result.scalar_one_or_none()
        if not task:
            log.error("task_runner.task_not_found")
            return
        if not task.is_active:
            log.info("task_runner.task_inactive")
            return

        # Create execution record
        execution = TaskExecution(
            task_id=task.id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(execution)
        await db.flush()

        config = task.task_config or {}
        model = config.get("model", settings.DEFAULT_MODEL)
        prompt = config.get("prompt", task.description or "")
        tool_names = config.get("tools", [])

        try:
            # Retrieve relevant memories
            memory_context = ""
            if memory_manager.enabled and prompt:
                memories = await memory_manager.search(str(task.user_id), prompt, limit=3)
                if memories:
                    memory_text = "\n".join(f"- {m['memory']}" for m in memories if m.get("memory"))
                    if memory_text:
                        memory_context = f"\n\nRelevant context from memory:\n{memory_text}"

            # Build messages
            system_content = f"{TASK_SYSTEM_PROMPT}{memory_context}"
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ]

            # Get tools schema if task uses tools
            tools = None
            if tool_names and tool_manager.has_tools:
                all_tools = tool_manager.get_tools_schema()
                if tool_names != ["*"]:
                    tools = [t for t in all_tools if t["function"]["name"] in tool_names]
                else:
                    tools = all_tools

            # Tool execution loop
            tool_calls_log = []
            response: LLMResponse = await llm_client.complete(messages, model, tools=tools)

            for _ in range(MAX_TOOL_ROUNDS):
                if not response.has_tool_calls:
                    break

                # Append assistant message
                messages.append({
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in response.tool_calls
                    ],
                })

                # Execute tools
                for tc in response.tool_calls:
                    try:
                        arguments = json.loads(tc.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_result = await tool_manager.execute_tool(tc.name, arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })
                    tool_calls_log.append({
                        "tool": tc.name,
                        "arguments": arguments,
                        "result": tool_result[:500],  # Truncate for log
                    })

                response = await llm_client.complete(messages, model, tools=tools)
            else:
                if response.has_tool_calls:
                    response = await llm_client.complete(messages, model, tools=None)

            # Update execution record
            execution.status = "success"
            execution.result = response.content
            execution.token_usage = response.usage.get("total_tokens")
            execution.llm_messages = messages
            execution.tool_calls_log = tool_calls_log if tool_calls_log else None

            log.info("task_runner.success", tokens=execution.token_usage)

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            log.exception("task_runner.failed")

        finally:
            execution.finished_at = datetime.now(timezone.utc)
            task.last_run_at = execution.finished_at
            await db.commit()
