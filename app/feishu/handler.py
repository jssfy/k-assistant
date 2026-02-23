"""
Shared Feishu message handling logic — used by both webhook and WS listener.

Provides:
- Event ID deduplication (bounded OrderedDict)
- Text extraction from webhook dict and SDK event object
- Message processing (LLM chat + reply)
"""

import json
import uuid
from collections import OrderedDict

import structlog

from app.config import settings
from app.db.session import async_session
from app.feishu.client import feishu_client

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Event ID dedup cache (shared across webhook & WS)
# ---------------------------------------------------------------------------
_seen_events: OrderedDict[str, None] = OrderedDict()
MAX_SEEN_EVENTS = 1000


def dedup_event(event_id: str) -> bool:
    """Return True if this event was already seen (duplicate)."""
    if event_id in _seen_events:
        return True
    _seen_events[event_id] = None
    if len(_seen_events) > MAX_SEEN_EVENTS:
        _seen_events.popitem(last=False)
    return False


# ---------------------------------------------------------------------------
# Text extraction — from raw dict (webhook path)
# ---------------------------------------------------------------------------
def extract_text_from_dict(event: dict) -> tuple[str | None, str | None, str | None, bool]:
    """Extract text, message_id, chat_type, and is_mentioned from webhook event dict.

    Returns:
        (text, message_id, chat_type, is_mentioned)
    """
    message = event.get("message", {})
    msg_type = message.get("message_type")
    message_id = message.get("message_id")
    chat_type = message.get("chat_type")  # "p2p" or "group"

    if msg_type != "text":
        return None, message_id, chat_type, False

    try:
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return None, message_id, chat_type, False

    # Check for @mentions
    mentions = message.get("mentions", [])
    is_mentioned = any(m.get("key") for m in mentions) if mentions else False

    # Remove @mention tags from text
    if mentions:
        for m in mentions:
            key = m.get("key", "")
            if key:
                text = text.replace(key, "").strip()

    return text, message_id, chat_type, is_mentioned


# ---------------------------------------------------------------------------
# Text extraction — from SDK P2ImMessageReceiveV1 (WS path)
# ---------------------------------------------------------------------------
def extract_text_from_sdk_event(data) -> tuple[str | None, str | None, str | None, bool]:
    """Extract text, message_id, chat_type, and is_mentioned from SDK event object.

    Args:
        data: lark_oapi.api.im.v1.P2ImMessageReceiveV1 event data

    Returns:
        (text, message_id, chat_type, is_mentioned)
    """
    event = data.event
    message = event.message
    message_id = message.message_id
    chat_type = message.chat_type  # "p2p" or "group"
    msg_type = message.message_type

    if msg_type != "text":
        return None, message_id, chat_type, False

    try:
        content = json.loads(message.content or "{}")
        text = content.get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return None, message_id, chat_type, False

    # Check for @mentions
    mentions = message.mentions or []
    is_mentioned = any(m.key for m in mentions) if mentions else False

    # Remove @mention tags from text
    if mentions:
        for m in mentions:
            if m.key:
                text = text.replace(m.key, "").strip()

    return text, message_id, chat_type, is_mentioned


# ---------------------------------------------------------------------------
# Message processing (LLM chat + reply)
# ---------------------------------------------------------------------------
async def process_feishu_message(text: str, message_id: str, chat_type: str) -> None:
    """Process a Feishu message: call LLM and reply.

    Args:
        text: User message text (already cleaned of @mention tags).
        message_id: Feishu message ID for replying.
        chat_type: "p2p" or "group".
    """
    log = logger.bind(message_id=message_id, chat_type=chat_type)
    log.info("feishu.message", text=text[:100])

    # Call LLM
    try:
        from app.core.chat import chat

        user_id = uuid.UUID(settings.DEFAULT_USER_ID)
        async with async_session() as db:
            _, assistant_msg = await chat(db, user_id, text)
            await db.commit()

        reply_content = assistant_msg.content or "Sorry, I couldn't generate a response."

    except Exception:
        log.exception("feishu.chat_failed")
        reply_content = "Sorry, an error occurred while processing your message."

    # Reply
    try:
        reply_json = json.dumps({"text": reply_content})
        await feishu_client.reply_message(message_id, "text", reply_json)
    except Exception:
        log.exception("feishu.reply_failed")
