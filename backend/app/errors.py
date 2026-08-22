from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code, code, message, retryable=False, internal_code=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.internal_code = internal_code or code


def error_response(request: Request, exc: AppError):
    trace_id = getattr(request.state, "trace_id", "trace-missing")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            },
            "trace_id": trace_id,
        },
    )
