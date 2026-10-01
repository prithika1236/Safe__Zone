from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger("safezone.errors")


class SafeZoneException(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


async def safezone_exception_handler(request: Request, exc: SafeZoneException):
    logger.error(f"SafeZoneException on {request.method} {request.url.path}: {exc.message} (status: {exc.status_code})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "message": exc.message,
                "details": exc.details
            }
        }
    )


async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "message": "An internal server error occurred.",
                "details": str(exc) if request.app.debug else "Please contact administrator."
            }
        }
    )
