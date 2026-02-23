from dataclasses import dataclass


@dataclass
class SendResult:
    channel: str  # e.g. "feishu"
    success: bool
    target: str  # webhook URL or chat_id
    error: str | None = None
