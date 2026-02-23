import asyncio
from functools import partial

import structlog

from app.config import settings

logger = structlog.get_logger()


def _parse_db_url(url: str) -> dict:
    """Parse DATABASE_URL into pgvector connection params."""
    # Remove asyncpg driver prefix: postgresql+asyncpg://user:pass@host:port/dbname
    clean = url.replace("+asyncpg", "")
    from urllib.parse import unquote, urlparse

    parsed = urlparse(clean)
    return {
        "dbname": parsed.path.lstrip("/"),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or "postgres"),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
    }


def _create_mem0():
    """Create Mem0 Memory instance (synchronous, called once)."""
    from mem0 import Memory

    db_params = _parse_db_url(settings.DATABASE_URL)

    config = {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                **db_params,
                "collection_name": settings.MEM0_COLLECTION_NAME,
                "embedding_model_dims": 384,
                "diskann": False,
                "hnsw": True,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "embedding_dims": 384,
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": settings.DEFAULT_MODEL,
                "openai_base_url": settings.LITELLM_BASE_URL,
                "api_key": settings.LITELLM_API_KEY,
            },
        },
    }

    return Memory.from_config(config)


class MemoryManager:
    """Async wrapper around Mem0 for persistent user memory."""

    def __init__(self):
        self._mem0 = None
        self._loop = None

    async def initialize(self):
        if not settings.MEM0_ENABLED:
            logger.info("memory.disabled")
            return

        try:
            loop = asyncio.get_running_loop()
            self._mem0 = await loop.run_in_executor(None, _create_mem0)
            self._loop = loop
            logger.info("memory.initialized", collection=settings.MEM0_COLLECTION_NAME)
        except Exception:
            logger.exception("memory.init_failed")
            self._mem0 = None

    @property
    def enabled(self) -> bool:
        return self._mem0 is not None

    async def _run_sync(self, fn, *args, **kwargs):
        """Run a synchronous Mem0 call in executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def add(self, user_id: str, content: str, metadata: dict | None = None) -> dict:
        """Store a memory for a user. Returns Mem0 result dict."""
        if not self.enabled:
            return {"results": []}

        try:
            result = await self._run_sync(
                self._mem0.add,
                content,
                user_id=user_id,
                metadata=metadata or {},
            )
            logger.info("memory.add", user_id=user_id, results=len(result.get("results", [])))
            return result
        except Exception:
            logger.exception("memory.add_failed", user_id=user_id)
            return {"results": []}

    async def search(self, user_id: str, query: str, limit: int = 5) -> list[dict]:
        """Search for relevant memories. Returns list of memory dicts."""
        if not self.enabled:
            return []

        try:
            result = await self._run_sync(
                self._mem0.search,
                query,
                user_id=user_id,
                limit=limit,
            )
            memories = result.get("results", [])
            logger.info("memory.search", user_id=user_id, query=query[:50], found=len(memories))
            return memories
        except Exception:
            logger.exception("memory.search_failed", user_id=user_id)
            return []

    async def list(self, user_id: str) -> list[dict]:
        """List all memories for a user."""
        if not self.enabled:
            return []

        try:
            result = await self._run_sync(
                self._mem0.get_all,
                user_id=user_id,
            )
            return result.get("results", [])
        except Exception:
            logger.exception("memory.list_failed", user_id=user_id)
            return []

    async def delete(self, memory_id: str) -> bool:
        """Delete a specific memory by ID."""
        if not self.enabled:
            return False

        try:
            await self._run_sync(self._mem0.delete, memory_id)
            logger.info("memory.delete", memory_id=memory_id)
            return True
        except Exception:
            logger.exception("memory.delete_failed", memory_id=memory_id)
            return False


memory_manager = MemoryManager()
