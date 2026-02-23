"""
Feishu output: send content via webhook or bot API.

- target is a URL → webhook mode
- target is a chat_id/open_id → bot API mode
"""

import json

import structlog

from app.feishu.client import feishu_client
from app.output.base import SendResult

logger = structlog.get_logger()


async def send_feishu(target: str, content: str) -> SendResult:
    """Send content to Feishu via auto-detected mode.

    Args:
        target: Webhook URL or receive_id (chat_id / open_id).
        content: Text content to send.
    """
    try:
        if target.startswith("http"):
            # Webhook mode
            await feishu_client.send_webhook(target, content)
        else:
            # Bot API mode — assume chat_id
            msg_content = json.dumps({"text": content})
            await feishu_client.send_message(target, "text", msg_content)

        logger.info("output.feishu.sent", target=target[:60])
        return SendResult(channel="feishu", success=True, target=target)

    except Exception as e:
        logger.exception("output.feishu.failed", target=target[:60])
        return SendResult(channel="feishu", success=False, target=target, error=str(e))
