import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.llm import LLMResponse, ToolCall, llm_client
from app.core.memory import memory_manager
from app.core.tools import tool_manager
from app.models.conversation import Conversation
from app.models.message import Message

logger = structlog.get_logger()

SYSTEM_PROMPT = "You are a helpful personal AI assistant. Be concise and clear in your responses."

MEMORY_PROMPT_TEMPLATE = (
    "{base_prompt}\n\n"
    "You have memory of past interactions with this user. "
    "Here is what you remember:\n{memories}\n"
    "Use these memories to personalize your responses when relevant."
)

MAX_TOOL_ROUNDS = 10

# C3 fix: prevent GC of fire-and-forget tasks
_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro):
    """Schedule a coroutine as a background task, preventing GC."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def get_or_create_conversation(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    model: str | None = None,
) -> Conversation:
    if conversation_id:
        result = await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(
        user_id=user_id,
        model=model or settings.DEFAULT_MODEL,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv, attribute_names=["messages"])
    return conv


async def _retrieve_memories(user_id: str, message: str) -> list[str]:
    """Search for relevant memories and return as list of strings."""
    if not memory_manager.enabled:
        return []

    memories = await memory_manager.search(user_id, message, limit=5)
    return [m["memory"] for m in memories if m.get("memory")]


def build_messages(
    conversation: Conversation, new_message: str, memories: list[str] | None = None
) -> list[dict]:
    system_content = SYSTEM_PROMPT
    if memories:
        memory_text = "\n".join(f"- {m}" for m in memories)
        system_content = MEMORY_PROMPT_TEMPLATE.format(
            base_prompt=SYSTEM_PROMPT, memories=memory_text
        )

    # S7 fix: ensure messages are in chronological order
    messages = [{"role": "system", "content": system_content}]
    sorted_msgs = sorted(conversation.messages, key=lambda m: m.created_at)
    for msg in sorted_msgs:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": new_message})
    return messages


async def _execute_tool_calls(tool_calls: list[ToolCall]) -> list[dict]:
    """Execute tool calls and return tool result messages for the LLM."""
    results = []
    for tc in tool_calls:
        try:
            arguments = json.loads(tc.arguments)
        except json.JSONDecodeError:
            arguments = {}

        result_text = await tool_manager.execute_tool(tc.name, arguments)
        results.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result_text,
        })
    return results


async def _store_memory(user_id: str, user_message: str, assistant_content: str):
    """Store conversation exchange as memory (fire-and-forget)."""
    if not memory_manager.enabled:
        return

    try:
        # I3 fix: truncate long content to avoid excessive LLM costs in Mem0
        max_len = 2000
        truncated = assistant_content[:max_len] if len(assistant_content) > max_len else assistant_content
        content = f"User: {user_message}\nAssistant: {truncated}"
        await memory_manager.add(user_id, content)
    except Exception:
        logger.exception("memory.store_failed", user_id=user_id)


async def _set_title(db: AsyncSession, conversation: Conversation, first_message: str):
    title = first_message[:80].split("\n")[0]
    if len(first_message) > 80:
        title += "..."
    conversation.title = title
    await db.flush()


def _get_tools() -> list[dict] | None:
    """Get tool schemas if tools are available, else None."""
    if tool_manager.has_tools:
        return tool_manager.get_tools_schema()
    return None


async def chat(
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    conversation_id: uuid.UUID | None = None,
    model: str | None = None,
) -> tuple[Conversation, Message]:
    """Non-streaming chat with tool execution loop."""
    conversation = await get_or_create_conversation(db, user_id, conversation_id, model)

    # Retrieve relevant memories
    memories = await _retrieve_memories(str(user_id), message)
    messages = build_messages(conversation, message, memories=memories)

    # Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    if not conversation.title:
        await _set_title(db, conversation, message)

    # Tool execution loop
    tools = _get_tools()
    response: LLMResponse = await llm_client.complete(messages, conversation.model, tools=tools)

    for _ in range(MAX_TOOL_ROUNDS):
        if not response.has_tool_calls:
            break

        # Append assistant message with tool calls to context
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

        # Execute tools and append results
        tool_results = await _execute_tool_calls(response.tool_calls)
        messages.extend(tool_results)

        # Next LLM call
        response = await llm_client.complete(messages, conversation.model, tools=tools)
    else:
        # I6 fix: if loop exhausted and still has tool calls, do one final call without tools
        if response.has_tool_calls:
            logger.warning("chat.max_tool_rounds_exhausted", rounds=MAX_TOOL_ROUNDS)
            response = await llm_client.complete(messages, conversation.model, tools=None)

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=response.content,
        model=conversation.model,
        token_usage=response.usage.get("total_tokens"),
    )
    db.add(assistant_msg)
    await db.flush()

    _fire_and_forget(_store_memory(str(user_id), message, response.content))

    return conversation, assistant_msg


async def chat_stream(
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    conversation_id: uuid.UUID | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Streaming chat with tool execution loop. Yields SSE events."""
    conversation = await get_or_create_conversation(db, user_id, conversation_id, model)

    # Retrieve relevant memories
    memories = await _retrieve_memories(str(user_id), message)
    messages = build_messages(conversation, message, memories=memories)

    # Save user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    if not conversation.title:
        await _set_title(db, conversation, message)

    # Stream metadata
    yield _sse_event("metadata", {
        "conversation_id": str(conversation.id),
        "model": conversation.model,
    })

    tools = _get_tools()
    full_content = ""

    try:
        exhausted = False
        for _ in range(MAX_TOOL_ROUNDS):
            tool_calls_in_round: list[ToolCall] = []
            round_content = ""

            async for item in llm_client.stream(messages, conversation.model, tools=tools):
                if isinstance(item, str):
                    round_content += item
                    full_content += item
                    yield _sse_event("message", {"content": item})
                elif isinstance(item, ToolCall):
                    tool_calls_in_round.append(item)

            if not tool_calls_in_round:
                break  # No tool calls, final response

            # Emit tool call events
            for tc in tool_calls_in_round:
                try:
                    args = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    args = {}
                yield _sse_event("tool_call", {"tool": tc.name, "arguments": args})

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": round_content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in tool_calls_in_round
                ],
            })

            # Execute tools
            tool_results = await _execute_tool_calls(tool_calls_in_round)
            messages.extend(tool_results)

            # Emit tool result events
            for tc, result in zip(tool_calls_in_round, tool_results):
                yield _sse_event("tool_result", {
                    "tool": tc.name,
                    "result": result["content"],
                })
        else:
            exhausted = True

        # I6 fix: if loop exhausted, do final non-tool call for text response
        if exhausted:
            logger.warning("chat_stream.max_tool_rounds_exhausted", rounds=MAX_TOOL_ROUNDS)
            async for item in llm_client.stream(messages, conversation.model, tools=None):
                if isinstance(item, str):
                    full_content += item
                    yield _sse_event("message", {"content": item})

    except Exception as e:
        logger.exception("chat_stream.error")
        yield _sse_event("error", {"message": str(e)})
        return

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=full_content,
        model=conversation.model,
    )
    db.add(assistant_msg)
    await db.flush()
    await db.commit()

    _fire_and_forget(_store_memory(str(user_id), message, full_content))

    yield _sse_event("done", {"message_id": str(assistant_msg.id)})


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
