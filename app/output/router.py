"""
Output router — dispatch task results to configured output channels.

Accepts a single output_config dict or a list of them.
Format: {"type": "feishu", "target": "https://..."}
"""

import structlog

from app.output.base import SendResult
from app.output.feishu import send_feishu

logger = structlog.get_logger()


async def dispatch(output_config: dict | list[dict], content: str) -> list[SendResult]:
    """Route content to one or more output channels.

    Args:
        output_config: Single config or list of configs.
            Each must have "type" and "target".
        content: Text content to dispatch.

    Returns:
        List of SendResult for each target.
    """
    if isinstance(output_config, dict):
        output_config = [output_config]

    results = []
    for cfg in output_config:
        channel_type = cfg.get("type")
        target = cfg.get("target", "")

        if channel_type == "feishu":
            result = await send_feishu(target, content)
        else:
            logger.warning("output.unknown_type", type=channel_type)
            result = SendResult(
                channel=channel_type or "unknown",
                success=False,
                target=target,
                error=f"Unknown output type: {channel_type}",
            )
        results.append(result)

    return results
