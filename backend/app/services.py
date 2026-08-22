import hashlib
import json
from datetime import datetime, timezone

from .database import audit, decode_row
from .errors import AppError


CASE_PUBLIC_MESSAGE = "无法访问该病例，请检查病例编号或联系管理员。"
STATUS_LABELS = {
    "materials_pending": ("资料待提交", "请补齐病例资料。"),
    "designing": ("方案设计中", "请等待方案设计完成。"),
    "design_pending_confirmation": ("方案待确认", "请确认方案或提交修改意见。"),
    "production_pending": ("待排产", "方案已确认，等待排产。"),
    "in_production": ("生产中", "请等待生产完成。"),
    "shipped": ("已发货", "请关注模拟物流进度。"),
    "in_wear": ("佩戴中", "请按既定流程复诊。"),
    "paused": ("已暂停", "请联系人工客服了解暂停原因。"),
    "completed": ("已完成", "当前病例流程已完成。"),
    "cancelled": ("已取消", "当前病例已终止。"),
}


def _active_membership(conn, user_id, org_id, role=None):
    sql = "SELECT * FROM memberships WHERE user_id=? AND organization_id=? AND status='active'"
    params = [user_id, org_id]
    if role:
        sql += " AND role=?"
        params.append(role)
    rows = conn.execute(sql, params).fetchall()
    now = datetime.now(timezone.utc)
    for row in rows:
        if row["valid_to"] is None or datetime.fromisoformat(row["valid_to"].replace("Z", "+00:00")) >= now:
            return row
    return None


def _require_active_user(conn, user_id):
    user = decode_row(conn.execute("SELECT data FROM users WHERE user_id=?", (user_id,)).fetchone())
    if not user:
        raise AppError(401, "AUTH_REQUIRED", "登录凭证无效，请重新登录。")
    if user["account_status"] == "frozen":
        raise AppError(403, "ACCOUNT_FROZEN", "账号当前不可用，请联系管理员。")
    if user["account_status"] != "active":
        raise AppError(403, "ACCOUNT_DISABLED", "账号当前不可用，请联系管理员。")
    return user


def authorize_case(conn, user_id, case_id, trace_id):
    try:
        _require_active_user(conn, user_id)
    except AppError as exc:
        audit(conn, trace_id, user_id, "case.read", "case", case_id, "denied", exc.internal_code)
        raise
    case = decode_row(conn.execute("SELECT data FROM cases WHERE case_id=?", (case_id,)).fetchone())
    if not case:
        audit(conn, trace_id, user_id, "case.read", "case", case_id, "denied", "CASE_NOT_FOUND")
        raise AppError(404, "CASE_UNAVAILABLE", CASE_PUBLIC_MESSAGE, internal_code="CASE_NOT_FOUND")
    org = decode_row(conn.execute("SELECT data FROM organizations WHERE organization_id=?", (case["organization_id"],)).fetchone())
    if not org or org["status"] != "active":
        audit(conn, trace_id, user_id, "case.read", "case", case_id, "denied", "ORGANIZATION_INACTIVE")
        raise AppError(403, "CASE_UNAVAILABLE", CASE_PUBLIC_MESSAGE, internal_code="ORGANIZATION_INACTIVE")
    membership = _active_membership(conn, user_id, case["organization_id"])
    if not membership:
        audit(conn, trace_id, user_id, "case.read", "case", case_id, "denied", "MEMBERSHIP_INACTIVE")
        raise AppError(403, "CASE_UNAVAILABLE", CASE_PUBLIC_MESSAGE, internal_code="MEMBERSHIP_INACTIVE")
    allowed = False
    internal_reason = "CASE_ACCESS_DENIED"
    if membership["role"] == "doctor":
        allowed = case["primary_doctor_user_id"] == user_id
    elif membership["role"] == "assistant":
        assignment = conn.execute(
            "SELECT * FROM assignments WHERE organization_id=? AND assistant_user_id=? AND doctor_user_id=? AND status='active'",
            (case["organization_id"], user_id, case["primary_doctor_user_id"]),
        ).fetchone()
        allowed = assignment is not None and (
            assignment["valid_to"] is None
            or datetime.fromisoformat(assignment["valid_to"].replace("Z", "+00:00")) >= datetime.now(timezone.utc)
        )
        internal_reason = "ASSIGNMENT_REQUIRED"
    if not allowed:
        audit(conn, trace_id, user_id, "case.read", "case", case_id, "denied", internal_reason)
        raise AppError(403, "CASE_UNAVAILABLE", CASE_PUBLIC_MESSAGE, internal_code=internal_reason)
    audit(conn, trace_id, user_id, "case.read", "case", case_id, "allowed", "ACCESS_GRANTED")
    return case


def case_response(case, trace_id):
    label, next_step = STATUS_LABELS[case["status"]]
    return {
        "case_id": case["case_id"],
        "status": case["status"],
        "status_label": label,
        "updated_at": case["updated_at"],
        "next_step": next_step,
        "trace_id": trace_id,
    }


def create_ticket(conn, actor_user_id, payload, idempotency_key, trace_id):
    _require_active_user(conn, actor_user_id)
    membership = _active_membership(conn, actor_user_id, payload.organization_id)
    if not membership:
        audit(conn, trace_id, actor_user_id, "ticket.create", "ticket", None, "denied", "MEMBERSHIP_INACTIVE")
        raise AppError(403, "TICKET_ACCESS_DENIED", "无法为该机构创建工单。")
    if payload.case_id:
        case = authorize_case(conn, actor_user_id, payload.case_id, trace_id)
        if case["organization_id"] != payload.organization_id:
            raise AppError(403, "TICKET_ACCESS_DENIED", "无法为该机构创建工单。")
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing_row = conn.execute("SELECT * FROM tickets WHERE idempotency_key=?", (idempotency_key,)).fetchone()
    if existing_row:
        if existing_row["request_hash"] != request_hash:
            raise AppError(409, "IDEMPOTENCY_CONFLICT", "同一请求标识对应了不同的工单内容。")
        return decode_row(existing_row), False
    next_number = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
    now = datetime.now(timezone.utc).isoformat()
    high_risk = payload.risk_level in ("high", "critical") or payload.ticket_type == "clinical_risk"
    ticket = {
        "ticket_id": f"TKT-RUN-{next_number:05d}",
        "ticket_type": payload.ticket_type,
        "priority": "P0" if high_risk else ("P1" if payload.risk_level == "medium" else "P2"),
        "status": "open",
        "organization_id": payload.organization_id,
        "reporter_user_id": actor_user_id,
        "case_id": payload.case_id,
        "assignee_user_id": "USR-SPT-001" if high_risk else None,
        "assignee_team": "high-risk-support" if high_risk else None,
        "summary": payload.summary,
        "description": payload.description,
        "evidence": payload.evidence,
        "risk_level": payload.risk_level,
        "source": payload.source,
        "idempotency_key": idempotency_key,
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
    }
    conn.execute(
        "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticket["ticket_id"], ticket["organization_id"], ticket["reporter_user_id"], ticket["assignee_user_id"], ticket["case_id"], ticket["status"], idempotency_key, request_hash, json.dumps(ticket, ensure_ascii=False)),
    )
    audit(conn, trace_id, actor_user_id, "ticket.create", "ticket", ticket["ticket_id"], "allowed", "CREATED")
    return ticket, True


def get_ticket(conn, actor_user_id, ticket_id, trace_id):
    _require_active_user(conn, actor_user_id)
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    if not row:
        raise AppError(404, "TICKET_NOT_FOUND", "无法访问该工单，请检查工单编号。")
    ticket = decode_row(row)
    allowed = actor_user_id in (ticket["reporter_user_id"], ticket.get("assignee_user_id"))
    if not allowed:
        membership = _active_membership(conn, actor_user_id, ticket["organization_id"], "support")
        allowed = membership is not None
    audit(conn, trace_id, actor_user_id, "ticket.read", "ticket", ticket_id, "allowed" if allowed else "denied", "ACCESS_GRANTED" if allowed else "TICKET_ACCESS_DENIED")
    if not allowed:
        raise AppError(404, "TICKET_NOT_FOUND", "无法访问该工单，请检查工单编号。")
    return ticket
