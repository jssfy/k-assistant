"""
Feishu WebSocket long-connection listener.

Runs lark_oapi.ws.Client in a daemon thread so no public URL is needed.
SDK handles authentication, heartbeat, and auto-reconnect.
Event callbacks are bridged to the main asyncio loop via run_coroutine_threadsafe().
"""

import asyncio
import threading

import lark_oapi as lark
import lark_oapi.ws.client as _ws_mod
import structlog
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from app.config import settings
from app.feishu.handler import dedup_event, extract_text_from_sdk_event, process_feishu_message

logger = structlog.get_logger()


def _run_ws_client(ws_client: lark.ws.Client) -> None:
    """Target for the daemon thread: create a fresh event loop and run the SDK client."""
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    # The SDK uses a module-level `loop` variable captured at import time.
    # Replace it so start() uses our fresh loop instead of the main thread's uvloop.
    _ws_mod.loop = new_loop
    ws_client.start()


class FeishuWSListener:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    async def initialize(self):
        """Start the WebSocket listener in a daemon thread."""
        self._loop = asyncio.get_running_loop()

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_receive)
            .build()
        )

        ws_client = lark.ws.Client(
            app_id=settings.FEISHU_APP_ID,
            app_secret=settings.FEISHU_APP_SECRET,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
            auto_reconnect=True,
        )

        self._thread = threading.Thread(
            target=_run_ws_client,
            args=(ws_client,),
            name="feishu-ws",
            daemon=True,
        )
        self._thread.start()
        logger.info("feishu.ws.started")

    def _on_message_receive(self, data: P2ImMessageReceiveV1) -> None:
        """Handle im.message.receive_v1 — called from the SDK thread (sync)."""
        try:
            # Dedup
            event_id = data.header.event_id if data.header else None
            if event_id and dedup_event(event_id):
                logger.debug("feishu.ws.duplicate_event", event_id=event_id)
                return

            # Extract text
            text, message_id, chat_type, is_mentioned = extract_text_from_sdk_event(data)

            if not text:
                return

            # In group chats, only respond to @mentions
            if chat_type == "group" and not is_mentioned:
                return

            # Bridge to asyncio loop
            if self._loop is None:
                logger.warning("feishu.ws.no_event_loop")
                return

            future = asyncio.run_coroutine_threadsafe(
                process_feishu_message(text, message_id, chat_type),
                self._loop,
            )
            future.result(timeout=120)

        except Exception:
            logger.exception("feishu.ws.handler_error")

    async def shutdown(self):
        """Clean up references. Daemon thread exits with the process."""
        self._loop = None
        self._thread = None
        logger.info("feishu.ws.stopped")


# Singleton
feishu_ws_listener = FeishuWSListener()
