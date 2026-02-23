"""
Feishu event webhook — receives messages from Feishu and replies via LLM.

Handles:
- URL verification challenge (type=url_verification)
- im.message.receive_v1 events (v2.0 schema)
- Event ID deduplication (shared with WS listener)
- @mention filtering for group chats
"""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.feishu.handler import dedup_event, extract_text_from_dict, process_feishu_message

logger = structlog.get_logger()
router = APIRouter(tags=["feishu"])


@router.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    """Handle incoming Feishu events."""
    body = await request.json()

    # 1. URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    # 2. Verify token
    header = body.get("header", {})
    token = header.get("token", "")
    if settings.FEISHU_VERIFICATION_TOKEN and token != settings.FEISHU_VERIFICATION_TOKEN:
        logger.warning("feishu.webhook.invalid_token")
        return JSONResponse(status_code=403, content={"error": "Invalid verification token"})

    # 3. Event ID dedup
    event_id = header.get("event_id", "")
    if event_id and dedup_event(event_id):
        logger.debug("feishu.webhook.duplicate_event", event_id=event_id)
        return {"code": 0}

    # 4. Parse event
    event_type = header.get("event_type", "")
    event = body.get("event", {})

    if event_type != "im.message.receive_v1":
        logger.debug("feishu.webhook.ignored_event", event_type=event_type)
        return {"code": 0}

    text, message_id, chat_type, is_mentioned = extract_text_from_dict(event)

    # Skip non-text messages
    if not text:
        return {"code": 0}

    # In group chats, only respond to @mentions
    if chat_type == "group" and not is_mentioned:
        return {"code": 0}

    # 5. Process via LLM and reply
    await process_feishu_message(text, message_id, chat_type)

    return {"code": 0}
