import uuid

from app.config import settings


async def get_current_user_id() -> uuid.UUID:
    """Phase 1: return hardcoded default user ID."""
    return uuid.UUID(settings.DEFAULT_USER_ID)
