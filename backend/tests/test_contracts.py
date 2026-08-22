import json
import sqlite3
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from app.config import DATABASE_PATH, PROJECT_ROOT
from app.main import DEMO_CASE_ALIASES, demo_ticket_alias, internal_ticket_id


def test_external_openapi_contract_has_required_operations():
    contract = yaml.safe_load((PROJECT_ROOT / "data/schemas/openapi.yaml").read_text(encoding="utf-8"))
    assert contract["openapi"] == "3.0.3"
    assert set(contract["paths"]) >= {"/health", "/v1/auth/token", "/v1/cases/{case_id}", "/v1/tickets", "/v1/tickets/{ticket_id}"}


def test_knowledge_and_eval_records_match_json_schemas():
    pairs = [
        ("knowledge.schema.json", "knowledge/documents.json"),
        ("eval.schema.json", "eval/eval_cases.json"),
    ]
    for schema_name, data_name in pairs:
        schema = json.loads((PROJECT_ROOT / f"data/schemas/{schema_name}").read_text(encoding="utf-8"))
        records = json.loads((PROJECT_ROOT / f"data/{data_name}").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        errors = [error.message for record in records for error in validator.iter_errors(record)]
        assert errors == []


def test_denied_case_access_writes_internal_audit_reason(client, auth_headers):
    response = client.get("/v1/cases/CASE-2026-0019", headers=auth_headers("USR-DOC-001"))
    assert response.status_code == 403
    with sqlite3.connect(DATABASE_PATH) as conn:
        reason = conn.execute(
            "SELECT internal_reason FROM audit_logs WHERE actor_user_id=? AND object_id=? ORDER BY audit_id DESC LIMIT 1",
            ("USR-DOC-001", "CASE-2026-0019"),
        ).fetchone()[0]
    assert reason == "CASE_ACCESS_DENIED"


def test_untrusted_identity_fields_cannot_override_token(client, auth_headers):
    response = client.get(
        "/v1/cases/CASE-2026-0019?user_id=USR-DOC-019&doctor_id=USR-DOC-019",
        headers=auth_headers("USR-DOC-001"),
    )
    assert response.status_code == 403


def test_demo_adapter_aliases_are_reversible():
    assert DEMO_CASE_ALIASES["A20260001"] == "CASE-2026-0025"
    assert demo_ticket_alias("TKT-RUN-00101") == "T20260101"
    assert internal_ticket_id("T20260101") == "TKT-RUN-00101"
