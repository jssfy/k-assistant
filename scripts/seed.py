"""Seed database with default user for Phase 1."""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.user import User

DEFAULT_USER_ID = uuid.UUID(settings.DEFAULT_USER_ID)


async def seed():
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == DEFAULT_USER_ID))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(id=DEFAULT_USER_ID, name="Default User")
            session.add(user)
            await session.commit()
            print(f"Created default user: {user.id}")
        else:
            print(f"Default user already exists: {user.id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
