import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, Header, Request, Response

from .auth import create_token, current_user_id
from .config import APP_VERSION, DEMO_USER_ID, ENABLE_DEMO_ADAPTER, ENABLE_FAULT_INJECTION, JWT_EXPIRE_MINUTES
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


def require_demo_adapter():
    if not ENABLE_DEMO_ADAPTER:
        raise AppError(404, "DEMO_ADAPTER_DISABLED", "Demo adapter is disabled.")


DEMO_CASE_ALIASES = {
    "A20260001": "CASE-2026-0025",
    "A20260002": "CASE-2026-0019",
    "A20260003": "CASE-2026-0049",
}


def demo_ticket_alias(ticket_id):
    if ticket_id.startswith("TKT-RUN-"):
        return f"T2026{int(ticket_id.rsplit('-', 1)[1]):04d}"
    return ticket_id


def internal_ticket_id(ticket_id):
    if ticket_id.startswith("T2026") and len(ticket_id) == 9 and ticket_id[1:].isdigit():
        return f"TKT-RUN-{int(ticket_id[-4:]):05d}"
    return ticket_id


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


@app.get("/v1/demo/cases/{case_id}", include_in_schema=False)
@app.get("/v1/demo/cases/{case_id}/status", include_in_schema=False)
def demo_case_status(request: Request, case_id: str):
    """Dify-only adapter for synthetic data; production clients use JWT endpoints."""
    require_demo_adapter()
    internal_case_id = DEMO_CASE_ALIASES.get(case_id, case_id)
    with connection() as conn:
        case = authorize_case(conn, DEMO_USER_ID, internal_case_id, request.state.trace_id)
        data = case_response(case, request.state.trace_id)
        data = {**data, "case_id": case_id, "internal_case_id": internal_case_id}
        return {"success": True, "data": data, "demo_identity": DEMO_USER_ID}


@app.post("/v1/demo/tickets", include_in_schema=False)
def demo_create_ticket(request: Request, response: Response, payload: dict = Body(...)):
    require_demo_adapter()
    raw_case_id = str(payload.get("case_id") or "")
    case_match = re.search(r"(?:[AB]\d{8}|CASE-\d{4}-\d{4})", raw_case_id, re.IGNORECASE)
    display_case_id = case_match.group(0).upper() if case_match else None
    case_id = DEMO_CASE_ALIASES.get(display_case_id, display_case_id)
    risk_signal = payload.get("risk_signal") or payload.get("problem_type") or ""
    risk_level = "high" if risk_signal else "medium"
    normalized = TicketCreate(
        ticket_type="clinical_risk" if risk_level == "high" else "service_request",
        organization_id="ORG-001",
        case_id=case_id,
        summary=payload.get("problem_summary") or "Dify 人工服务请求",
        description=payload.get("conversation_excerpt") or payload.get("problem_summary") or "模拟请求",
        evidence=[value for value in [payload.get("product_line"), payload.get("current_stage")] if value],
        risk_level=risk_level,
        source="dify",
    )
    canonical = json.dumps(normalized.model_dump(), ensure_ascii=False, sort_keys=True)
    idempotency_key = "dify-demo-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    with connection() as conn:
        ticket, created = create_ticket(conn, DEMO_USER_ID, normalized, idempotency_key, request.state.trace_id)
        response.status_code = 201 if created else 200
        alias = demo_ticket_alias(ticket["ticket_id"])
        data = {**ticket, "ticket_id": alias, "internal_ticket_id": ticket["ticket_id"]}
        return {"success": True, **data, "data": data, "trace_id": request.state.trace_id}


@app.get("/v1/demo/tickets/{ticket_id}", include_in_schema=False)
def demo_read_ticket(request: Request, ticket_id: str):
    require_demo_adapter()
    internal_id = internal_ticket_id(ticket_id)
    with connection() as conn:
        ticket = get_ticket(conn, DEMO_USER_ID, internal_id, request.state.trace_id)
        data = {**ticket, "ticket_id": ticket_id, "internal_ticket_id": internal_id}
        return {"success": True, **data, "data": data, "trace_id": request.state.trace_id}
