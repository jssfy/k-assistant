"""
Natural language to scheduled task parser.

Uses LLM function calling to extract cron expression and task config
from user's natural language description.
"""

import json

import structlog

from app.core.llm import llm_client
from app.config import settings

logger = structlog.get_logger()

SCHEDULE_TOOL = {
    "type": "function",
    "function": {
        "name": "create_scheduled_task",
        "description": "Parse a natural language task description into a structured scheduled task configuration.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short, descriptive name for the task (e.g. 'Weekly AI News Summary')",
                },
                "cron_expression": {
                    "type": "string",
                    "description": (
                        "5-field cron expression for the schedule. "
                        "Format: minute hour day_of_month month day_of_week. "
                        "The cron should be in the user's local timezone (not UTC). "
                        "Examples: '0 9 * * 1' = every Monday 9am, '30 8 * * *' = every day 8:30am"
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "The detailed prompt/instructions to execute on each run",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool names needed (e.g. ['web_search']). Empty if no tools needed.",
                },
                "model": {
                    "type": "string",
                    "description": "Preferred model for this task. Use 'claude-sonnet' as default.",
                },
            },
            "required": ["name", "cron_expression", "prompt"],
        },
    },
}


async def parse_task_description(
    description: str,
    timezone: str = "Asia/Shanghai",
    available_tools: list[str] | None = None,
) -> dict:
    """
    Parse natural language into structured task config using LLM function calling.

    Returns dict with keys: name, cron_expression, prompt, tools, model
    """
    tools_hint = ""
    if available_tools:
        tools_hint = f"\nAvailable tools: {', '.join(available_tools)}"

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a task scheduling assistant. The user's timezone is {timezone}. "
                "Parse their request into a scheduled task configuration. "
                "The cron expression should be in the user's local timezone. "
                "Be precise with the schedule - if user says 'every morning' use 9:00, "
                "'every evening' use 18:00. "
                f"For 'every weekday' use day_of_week 1-5.{tools_hint}"
            ),
        },
        {"role": "user", "content": description},
    ]

    response = await llm_client.complete(
        messages,
        model=settings.DEFAULT_MODEL,
        tools=[SCHEDULE_TOOL],
    )

    if not response.has_tool_calls:
        # LLM didn't use function calling - try to extract from text
        logger.warning("nl_parser.no_tool_call", response=response.content[:200])
        raise ValueError(
            "Could not parse task schedule from description. "
            "Please provide a clearer description with schedule info."
        )

    tc = response.tool_calls[0]
    parsed = json.loads(tc.arguments)

    # Ensure required fields
    result = {
        "name": parsed.get("name", "Unnamed Task"),
        "cron_expression": parsed["cron_expression"],
        "prompt": parsed["prompt"],
        "tools": parsed.get("tools", []),
        "model": parsed.get("model", settings.DEFAULT_MODEL),
    }

    logger.info(
        "nl_parser.parsed",
        name=result["name"],
        cron=result["cron_expression"],
        tools=result["tools"],
    )
    return result
