import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request, Response

from .auth import create_token, current_user_id
from .config import APP_VERSION, ENABLE_FAULT_INJECTION, JWT_EXPIRE_MINUTES
from .database import connection, decode_row, initialize_database
from .errors import AppError, error_response
from .models import TicketCreate, TokenRequest, TokenResponse
from .services import authorize_case, case_response, create_ticket, get_ticket


@asynccontextmanager
async def lifespan(_app):
    initialize_database()
    yield


app = FastAPI(title="Enterprise Customer Service Mock API", version=APP_VERSION, lifespan=lifespan)
logger = logging.getLogger("customer_service.api")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-ID") or f"trace-{uuid.uuid4()}"
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Trace-ID"] = request.state.trace_id
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    logger.info(json.dumps({
        "event": "http_request",
        "trace_id": request.state.trace_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }, ensure_ascii=False))
    return response


@app.exception_handler(AppError)
async def handle_app_error(request, exc):
    return error_response(request, exc)


async def maybe_inject_fault(mode):
    if not ENABLE_FAULT_INJECTION or not mode:
        return
    if mode == "timeout":
        await asyncio.sleep(12)
    status_by_mode = {f"http_{code}": code for code in (400, 401, 403, 404, 409, 429, 500)}
    if mode in status_by_mode:
        status = status_by_mode[mode]
        raise AppError(status, f"INJECTED_{status}", "测试故障已注入。", retryable=status in (429, 500))
    if mode == "database_unavailable":
        raise AppError(503, "DEPENDENCY_UNAVAILABLE", "服务暂时不可用，请稍后重试。", retryable=True)


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.post("/v1/auth/token", response_model=TokenResponse)
def token(payload: TokenRequest):
    with connection() as conn:
        user = decode_row(conn.execute("SELECT data FROM users WHERE user_id=?", (payload.user_id,)).fetchone())
    if not user:
        raise AppError(401, "AUTH_REQUIRED", "模拟用户不存在。")
    return TokenResponse(access_token=create_token(payload.user_id), expires_in=JWT_EXPIRE_MINUTES * 60)


@app.get("/v1/cases/{case_id}")
async def read_case(
    request: Request,
    case_id: str,
    user_id: str = Depends(current_user_id),
    x_fault_mode: str = Header(default=None),
):
    await maybe_inject_fault(x_fault_mode)
    with connection() as conn:
        case = authorize_case(conn, user_id, case_id, request.state.trace_id)
        return case_response(case, request.state.trace_id)


@app.post("/v1/tickets")
async def post_ticket(
    request: Request,
    response: Response,
    payload: TicketCreate,
    user_id: str = Depends(current_user_id),
    idempotency_key: str = Header(min_length=8, max_length=128),
    x_fault_mode: str = Header(default=None),
):
    await maybe_inject_fault(x_fault_mode)
    with connection() as conn:
        ticket, created = create_ticket(conn, user_id, payload, idempotency_key, request.state.trace_id)
        response.status_code = 201 if created else 200
        return {**ticket, "trace_id": request.state.trace_id}


@app.get("/v1/tickets/{ticket_id}")
async def read_ticket(
    request: Request,
    ticket_id: str,
    user_id: str = Depends(current_user_id),
    x_fault_mode: str = Header(default=None),
):
    await maybe_inject_fault(x_fault_mode)
    with connection() as conn:
        ticket = get_ticket(conn, user_id, ticket_id, request.state.trace_id)
        return {**ticket, "trace_id": request.state.trace_id}
