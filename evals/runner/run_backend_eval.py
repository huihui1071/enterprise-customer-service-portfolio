"""Run deterministic backend evaluations and write a measured JSON report."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
REPORT_DIR = PROJECT_ROOT / "evals" / "reports"
EVAL_DB = PROJECT_ROOT / "evals" / "runner" / "eval_customer_service.db"

os.environ["DATABASE_PATH"] = str(EVAL_DB)
os.environ["JWT_SECRET"] = "eval-only-secret"
os.environ["ENABLE_FAULT_INJECTION"] = "true"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import app


def auth_headers(client, user_id):
    response = client.post("/v1/auth/token", json={"user_id": user_id})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def run():
    initialize_database(force=True)
    access_cases = json.loads((PROJECT_ROOT / "data/boundary/access_cases.json").read_text(encoding="utf-8"))
    results = []
    with TestClient(app) as client:
        for item in access_cases:
            response = client.get(
                f"/v1/cases/{item['case_id']}",
                headers={**auth_headers(client, item["actor_user_id"]), "X-Trace-ID": f"eval-{item['test_id']}"},
            )
            actual = "allow" if response.status_code == 200 else "deny"
            results.append({
                "test_id": item["test_id"],
                "expected": item["expected"],
                "actual": actual,
                "http_status": response.status_code,
                "passed": actual == item["expected"],
            })

        ticket_payload = {
            "ticket_type": "system_issue",
            "organization_id": "ORG-001",
            "summary": "Eval idempotency",
            "description": "Synthetic evaluation request",
            "evidence": [],
            "risk_level": "low",
            "source": "api",
        }
        idem_headers = {**auth_headers(client, "USR-DOC-001"), "Idempotency-Key": "eval-idem-0001"}
        first = client.post("/v1/tickets", headers=idem_headers, json=ticket_payload)
        second = client.post("/v1/tickets", headers=idem_headers, json=ticket_payload)
        idempotency_passed = first.status_code == 201 and second.status_code == 200 and first.json()["ticket_id"] == second.json()["ticket_id"]

        risk_headers = {**auth_headers(client, "USR-DOC-001"), "Idempotency-Key": "eval-risk-0001"}
        risk = client.post("/v1/tickets", headers=risk_headers, json={
            "ticket_type": "clinical_risk",
            "organization_id": "ORG-001",
            "case_id": "CASE-2026-0025",
            "summary": "Synthetic high-risk escalation",
            "description": "Synthetic evidence only",
            "evidence": ["mock://evidence/eval-risk"],
            "risk_level": "high",
            "source": "api",
        })
        risk_passed = risk.status_code == 201 and risk.json()["priority"] == "P0" and risk.json()["assignee_team"] == "high-risk-support"

    passed_access = sum(1 for item in results if item["passed"])
    denied_cases = [item for item in results if item["expected"] == "deny"]
    unauthorized_successes = sum(1 for item in denied_cases if item["actual"] == "allow")
    report = {
        "report_type": "backend_eval",
        "metric_status": "measured",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": "synthetic-v1",
        "summary": {
            "access_decision_accuracy": passed_access / len(results),
            "access_cases_passed": passed_access,
            "access_cases_total": len(results),
            "unauthorized_access_successes": unauthorized_successes,
            "idempotency_passed": idempotency_passed,
            "high_risk_assignment_passed": risk_passed,
        },
        "limitations": [
            "Only the deterministic Mock Backend is measured in this report.",
            "AI route accuracy, RAG quality, and high-risk recall remain unmeasured until Dify batch evaluation runs.",
            "All users, organizations, cases, and tickets are synthetic.",
        ],
        "access_results": results,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / "backend-eval-latest.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if EVAL_DB.exists():
        EVAL_DB.unlink()
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if all([
        result["summary"]["access_decision_accuracy"] == 1,
        result["summary"]["unauthorized_access_successes"] == 0,
        result["summary"]["idempotency_passed"],
        result["summary"]["high_risk_assignment_passed"],
    ]) else 1)
