"""
Feishu API client — singleton, same pattern as MemoryManager/ToolManager.

Handles:
- tenant_access_token lifecycle (auto-refresh with 5-min buffer)
- Bot API: send_message, reply_message
- Webhook: send_webhook (no auth needed)
"""

import asyncio
import time

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

FEISHU_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
TOKEN_REFRESH_BUFFER = 300  # refresh 5 minutes before expiry


class FeishuClient:
    def __init__(self):
        self._http: httpx.AsyncClient | None = None
        self._token: str = ""
        self._token_expires_at: float = 0
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Create httpx client and fetch the first token."""
        self._http = httpx.AsyncClient(timeout=30)
        await self._refresh_token()
        logger.info("feishu.initialized")

    async def shutdown(self):
        """Close httpx client."""
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info("feishu.shutdown")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _refresh_token(self):
        """Fetch a new tenant_access_token from Feishu."""
        async with self._lock:
            # Double-check after acquiring lock
            if self._token and time.time() < self._token_expires_at - TOKEN_REFRESH_BUFFER:
                return

            resp = await self._http.post(
                TOKEN_URL,
                json={
                    "app_id": settings.FEISHU_APP_ID,
                    "app_secret": settings.FEISHU_APP_SECRET,
                },
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error("feishu.token_refresh_failed", detail=data)
                raise RuntimeError(f"Feishu token refresh failed: {data.get('msg')}")

            self._token = data["tenant_access_token"]
            expire = data.get("expire", 7200)
            self._token_expires_at = time.time() + expire
            logger.info("feishu.token_refreshed", expires_in=expire)

    async def _ensure_token(self):
        """Ensure token is valid, refresh if needed."""
        if time.time() >= self._token_expires_at - TOKEN_REFRESH_BUFFER:
            await self._refresh_token()

    async def _authed_request(self, method: str, url: str, **kwargs) -> dict:
        """Make an authenticated request to Feishu API."""
        await self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token}"
        resp = await self._http.request(method, url, headers=headers, **kwargs)
        return resp.json()

    # ------------------------------------------------------------------
    # Bot API
    # ------------------------------------------------------------------

    async def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: str,
        receive_id_type: str = "chat_id",
    ) -> dict:
        """Send a message via Bot API.

        Args:
            receive_id: Target ID (chat_id, open_id, etc.)
            msg_type: "text", "interactive", etc.
            content: JSON string of message content.
            receive_id_type: "chat_id" | "open_id" | "user_id" | "union_id"
        """
        url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type={receive_id_type}"
        data = await self._authed_request(
            "POST",
            url,
            json={"receive_id": receive_id, "msg_type": msg_type, "content": content},
        )
        if data.get("code") != 0:
            logger.error("feishu.send_message_failed", detail=data)
        return data

    async def reply_message(self, message_id: str, msg_type: str, content: str) -> dict:
        """Reply to a specific message via Bot API."""
        url = f"{FEISHU_BASE}/im/v1/messages/{message_id}/reply"
        data = await self._authed_request(
            "POST",
            url,
            json={"msg_type": msg_type, "content": content},
        )
        if data.get("code") != 0:
            logger.error("feishu.reply_message_failed", detail=data)
        return data

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    async def send_webhook(self, webhook_url: str, text: str) -> dict:
        """Send a text message via incoming webhook (no auth needed)."""
        resp = await self._http.post(
            webhook_url,
            json={"msg_type": "text", "content": {"text": text}},
        )
        data = resp.json()
        if data.get("code") != 0 and data.get("StatusCode") != 0:
            logger.error("feishu.webhook_failed", detail=data)
        return data


# Singleton instance
feishu_client = FeishuClient()
