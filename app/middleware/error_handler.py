import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path, method=request.method)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )
