import sqlite3

from app.config import DATABASE_PATH


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Trace-ID"].startswith("trace-")
    assert float(response.headers["X-Process-Time-Ms"]) >= 0


def test_doctor_can_read_own_case(client, auth_headers):
    response = client.get("/v1/cases/CASE-2026-0025", headers=auth_headers("USR-DOC-001"))
    assert response.status_code == 200
    assert response.json()["case_id"] == "CASE-2026-0025"


def test_doctor_cannot_read_colleague_case(client, auth_headers):
    response = client.get("/v1/cases/CASE-2026-0019", headers=auth_headers("USR-DOC-001"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CASE_UNAVAILABLE"


def test_assistant_can_read_assigned_doctor_case(client, auth_headers):
    response = client.get("/v1/cases/CASE-2026-0025", headers=auth_headers("USR-AST-001"))
    assert response.status_code == 200


def test_unassigned_assistant_is_denied(client, auth_headers):
    response = client.get("/v1/cases/CASE-2026-0025", headers=auth_headers("USR-AST-012"))
    assert response.status_code == 403


def test_departed_and_frozen_doctors_are_denied(client, auth_headers):
    departed = client.get("/v1/cases/CASE-2026-0001", headers=auth_headers("USR-DOC-025"))
    frozen = client.get("/v1/cases/CASE-2026-0006", headers=auth_headers("USR-DOC-028"))
    assert departed.status_code == 403
    assert frozen.status_code == 403
    assert frozen.json()["error"]["code"] == "ACCOUNT_FROZEN"


def test_missing_and_forbidden_cases_share_public_message(client, auth_headers):
    headers = auth_headers("USR-DOC-001")
    missing = client.get("/v1/cases/CASE-9999-9999", headers=headers)
    forbidden = client.get("/v1/cases/CASE-2026-0019", headers=headers)
    assert missing.json()["error"]["message"] == forbidden.json()["error"]["message"]


def test_ticket_creation_is_idempotent(client, auth_headers):
    headers = {**auth_headers("USR-DOC-001"), "Idempotency-Key": "idem-test-0001"}
    payload = {
        "ticket_type": "system_issue",
        "organization_id": "ORG-001",
        "summary": "模拟登录故障",
        "description": "无法登录模拟系统",
        "evidence": [],
        "risk_level": "low",
        "source": "dify"
    }
    first = client.post("/v1/tickets", headers=headers, json=payload)
    second = client.post("/v1/tickets", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["ticket_id"] == second.json()["ticket_id"]
    with sqlite3.connect(DATABASE_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tickets WHERE idempotency_key='idem-test-0001'").fetchone()[0] == 1


def test_idempotency_key_rejects_different_payload(client, auth_headers):
    headers = {**auth_headers("USR-DOC-001"), "Idempotency-Key": "idem-test-0002"}
    base = {
        "ticket_type": "system_issue", "organization_id": "ORG-001",
        "summary": "问题一", "description": "描述", "evidence": [],
        "risk_level": "low", "source": "dify"
    }
    assert client.post("/v1/tickets", headers=headers, json=base).status_code == 201
    base["summary"] = "问题二"
    assert client.post("/v1/tickets", headers=headers, json=base).status_code == 409


def test_high_risk_ticket_is_assigned_immediately(client, auth_headers):
    headers = {**auth_headers("USR-DOC-001"), "Idempotency-Key": "idem-risk-0001"}
    response = client.post("/v1/tickets", headers=headers, json={
        "ticket_type": "clinical_risk", "organization_id": "ORG-001",
        "case_id": "CASE-2026-0025", "summary": "模拟高风险异常",
        "description": "仅用于测试", "evidence": ["mock://evidence/test"],
        "risk_level": "high", "source": "dify"
    })
    assert response.status_code == 201
    assert response.json()["priority"] == "P0"
    assert response.json()["assignee_team"] == "high-risk-support"


def test_fault_injection(client, auth_headers):
    headers = {**auth_headers("USR-DOC-001"), "X-Fault-Mode": "http_500"}
    response = client.get("/v1/cases/CASE-2026-0025", headers=headers)
    assert response.status_code == 500
    assert response.json()["error"]["retryable"] is True


def test_demo_adapter_fault_injection(client, monkeypatch):
    monkeypatch.setattr("app.main.ENABLE_DEMO_ADAPTER", True)
    response = client.get(
        "/v1/demo/cases/A20260001/status",
        headers={"X-Fault-Mode": "http_429"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "INJECTED_429"
    assert response.json()["error"]["retryable"] is True


def test_demo_adapter_authorization_revocation_boundary(client, monkeypatch):
    monkeypatch.setattr("app.main.ENABLE_DEMO_ADAPTER", True)
    allowed = client.get("/v1/demo/cases/A20260001/status")
    revoked = client.get(
        "/v1/demo/cases/A20260001/status",
        headers={"X-Fault-Mode": "authorization_revoked"},
    )
    assert allowed.status_code == 200
    assert revoked.status_code == 403
    assert revoked.json()["error"]["code"] == "CASE_UNAVAILABLE"
    assert revoked.json()["error"]["retryable"] is False


def test_demo_adapter_is_disabled_by_default(client):
    response = client.get("/v1/demo/cases/CASE-2026-0025/status")
    assert response.status_code == 404
