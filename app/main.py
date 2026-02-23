from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.tasks import router as tasks_router
from app.config import settings
from app.core.memory import memory_manager
from app.core.tools import tool_manager
from app.feishu.client import feishu_client
from app.feishu.webhook import router as feishu_router
from app.feishu.ws_listener import feishu_ws_listener
from app.middleware.error_handler import global_exception_handler
from app.middleware.logging import LoggingMiddleware
from app.scheduler.engine import scheduler_engine


logger = structlog.get_logger()


def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            (
                structlog.dev.ConsoleRenderer()
                if settings.APP_ENV == "development"
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def _sync_scheduler_tasks():
    """Restore active tasks from DB into the scheduler after restart."""
    from sqlalchemy import select
    from app.db.session import async_session
    from app.models.scheduled_task import ScheduledTask

    async with async_session() as db:
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.is_active.is_(True))
        )
        tasks = result.scalars().all()
        for task in tasks:
            scheduler_engine.add_task(task.id, task.cron_expression, task.timezone)
        if tasks:
            logger.info("scheduler.synced_tasks", count=len(tasks))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("app.startup", env=settings.APP_ENV)

    # Initialize Phase 2 subsystems
    await memory_manager.initialize()
    await tool_manager.initialize()

    # Initialize Phase 3: Scheduler
    if settings.SCHEDULER_ENABLED:
        scheduler_engine.start()
        # Sync active tasks from DB to scheduler
        await _sync_scheduler_tasks()

    # Initialize Phase 4: Feishu
    if settings.FEISHU_ENABLED:
        await feishu_client.initialize()
        await feishu_ws_listener.initialize()

    yield

    # Shutdown
    if settings.FEISHU_ENABLED:
        await feishu_ws_listener.shutdown()
        await feishu_client.shutdown()
    if settings.SCHEDULER_ENABLED:
        scheduler_engine.shutdown()
    await tool_manager.shutdown()
    logger.info("app.shutdown")


app = FastAPI(title="K-Assistant", lifespan=lifespan)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

# Exception handler
app.add_exception_handler(Exception, global_exception_handler)

# Routes
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(feishu_router)

# Serve static files (built frontend) if available
static_dir = Path(__file__).parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}
