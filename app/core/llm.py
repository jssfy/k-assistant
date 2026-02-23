from collections.abc import AsyncIterator

import structlog
from openai import AsyncOpenAI

from app.config import settings

logger = structlog.get_logger()


class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url=settings.LITELLM_BASE_URL,
            api_key=settings.LITELLM_API_KEY,
        )

    async def complete(
        self, messages: list[dict], model: str | None = None
    ) -> tuple[str, dict]:
        """Non-streaming completion. Returns (content, usage_dict)."""
        model = model or settings.DEFAULT_MODEL
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
        )
        content = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.info("llm.complete", model=model, **usage)
        return content, usage

    async def stream(
        self, messages: list[dict], model: str | None = None
    ) -> AsyncIterator[str]:
        """Streaming completion. Yields content deltas."""
        model = model or settings.DEFAULT_MODEL
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

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
