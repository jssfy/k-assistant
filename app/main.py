from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.config import settings
from app.middleware.error_handler import global_exception_handler
from app.middleware.logging import LoggingMiddleware


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger = structlog.get_logger()
    logger.info("app.startup", env=settings.APP_ENV)
    yield
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

# Serve static files (built frontend) if available
static_dir = Path(__file__).parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}
