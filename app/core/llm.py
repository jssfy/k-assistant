from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import structlog
from openai import AsyncOpenAI

from app.config import settings

logger = structlog.get_logger()


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url=settings.LITELLM_BASE_URL,
            api_key=settings.LITELLM_API_KEY,
        )

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Non-streaming completion. Returns LLMResponse with content and/or tool_calls."""
        model = model or settings.DEFAULT_MODEL

        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.info("llm.complete", model=model, **usage)

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            usage=usage,
        )

    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str | ToolCall]:
        """Streaming completion. Yields content deltas (str) or accumulated ToolCall objects."""
        model = model or settings.DEFAULT_MODEL

        kwargs = {"model": model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)

        # Accumulate tool calls across chunks
        pending_tool_calls: dict[int, dict] = {}

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Stream text content
            if delta.content:
                yield delta.content

            # Accumulate tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in pending_tool_calls:
                        pending_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        pending_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            pending_tool_calls[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            pending_tool_calls[idx]["arguments"] += tc_delta.function.arguments

        # Yield completed tool calls at the end
        for tc_data in pending_tool_calls.values():
            yield ToolCall(
                id=tc_data["id"],
                name=tc_data["name"],
                arguments=tc_data["arguments"],
            )

    async def list_models(self) -> list[dict]:
        """List available models from LiteLLM."""
        try:
            response = await self.client.models.list()
            return [
                {"id": m.id, "owned_by": m.owned_by}
                for m in response.data
            ]
        except Exception:
            logger.exception("llm.list_models_failed")
            return []


llm_client = LLMClient()
