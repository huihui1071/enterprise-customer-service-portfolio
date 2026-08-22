"""Validate referential, temporal, uniqueness, and portfolio coverage rules."""

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate():
    orgs = load("seed/organizations.json")
    users = load("seed/users.json")
    memberships = load("seed/memberships.json")
    assignments = load("seed/assistant_doctor_assignments.json")
    cases = load("seed/cases.json")
    case_events = load("seed/case_status_events.json")
    tickets = load("seed/tickets.json")
    ticket_events = load("seed/ticket_events.json")
    knowledge = load("knowledge/documents.json")
    eval_cases = load("eval/eval_cases.json")

    errors = []
    user_ids = {item["user_id"] for item in users}
    org_ids = {item["organization_id"] for item in orgs}
    case_ids = {item["case_id"] for item in cases}
    ticket_ids = {item["ticket_id"] for item in tickets}

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(len(user_ids) == len(users), "duplicate user_id")
    require(len(org_ids) == len(orgs), "duplicate organization_id")
    require(len(case_ids) == len(cases), "duplicate case_id")
    require(len(ticket_ids) == len(tickets), "duplicate ticket_id")
    require(len({item["organization_code"] for item in orgs}) == len(orgs), "duplicate organization_code")
    require(len({item["idempotency_key"] for item in tickets}) == len(tickets), "duplicate idempotency_key")

    membership_lookup = {}
    for item in memberships:
        require(item["user_id"] in user_ids, f"membership missing user: {item['membership_id']}")
        require(item["organization_id"] in org_ids, f"membership missing org: {item['membership_id']}")
        if item["valid_to"]:
            require(parse(item["valid_to"]) >= parse(item["valid_from"]), f"invalid membership dates: {item['membership_id']}")
        membership_lookup[(item["user_id"], item["organization_id"], item["role"])] = item

    for item in assignments:
        require(item["assistant_user_id"] in user_ids, f"assignment missing assistant: {item['assignment_id']}")
        require(item["doctor_user_id"] in user_ids, f"assignment missing doctor: {item['assignment_id']}")
        require(item["organization_id"] in org_ids, f"assignment missing org: {item['assignment_id']}")
        require((item["assistant_user_id"], item["organization_id"], "assistant") in membership_lookup, f"assistant membership missing: {item['assignment_id']}")
        require((item["doctor_user_id"], item["organization_id"], "doctor") in membership_lookup, f"doctor membership missing: {item['assignment_id']}")

    for item in cases:
        require(item["organization_id"] in org_ids, f"case missing org: {item['case_id']}")
        require(item["primary_doctor_user_id"] in user_ids, f"case missing doctor: {item['case_id']}")
        require((item["primary_doctor_user_id"], item["organization_id"], "doctor") in membership_lookup, f"case doctor org mismatch: {item['case_id']}")
        require(parse(item["updated_at"]) >= parse(item["created_at"]), f"case time reversed: {item['case_id']}")

    case_created = {item["case_id"]: parse(item["created_at"]) for item in cases}
    for item in case_events:
        require(item["case_id"] in case_ids, f"event missing case: {item['event_id']}")
        require(parse(item["created_at"]) >= case_created[item["case_id"]], f"case event predates case: {item['event_id']}")

    ticket_created = {item["ticket_id"]: parse(item["created_at"]) for item in tickets}
    for item in tickets:
        require(item["organization_id"] in org_ids, f"ticket missing org: {item['ticket_id']}")
        require(item["reporter_user_id"] in user_ids, f"ticket missing reporter: {item['ticket_id']}")
        require(item["case_id"] is None or item["case_id"] in case_ids, f"ticket missing case: {item['ticket_id']}")
        require(item["assignee_user_id"] is None or item["assignee_user_id"] in user_ids, f"ticket missing assignee: {item['ticket_id']}")
        if item["status"] in ("resolved", "closed"):
            require(item["resolved_at"] is not None, f"resolved ticket missing resolved_at: {item['ticket_id']}")
        require(parse(item["updated_at"]) >= parse(item["created_at"]), f"ticket time reversed: {item['ticket_id']}")
    for item in ticket_events:
        require(item["ticket_id"] in ticket_ids, f"event missing ticket: {item['event_id']}")
        require(parse(item["created_at"]) >= ticket_created[item["ticket_id"]], f"ticket event predates ticket: {item['event_id']}")

    require(len(users) == 55, f"expected 55 users, got {len(users)}")
    require(len(orgs) == 10, f"expected 10 orgs, got {len(orgs)}")
    require(len(cases) == 200, f"expected 200 cases, got {len(cases)}")
    require(len(tickets) == 100, f"expected 100 tickets, got {len(tickets)}")
    require(sum(1 for item in users if item["account_status"] == "frozen") >= 3, "missing frozen users")
    require(sum(1 for item in memberships if item["status"] == "inactive") >= 3, "missing departed memberships")
    require(sum(1 for item in tickets if item["ticket_type"] == "clinical_risk") >= 20, "missing clinical risk tickets")
    require(len(knowledge) == 30, f"expected 30 knowledge docs, got {len(knowledge)}")
    require({item["knowledge_domain"] for item in knowledge} == {"product", "service_flow", "system_usage", "clinical_term", "training"}, "knowledge domains incomplete")
    require(any(item["status"] == "expired" for item in knowledge), "missing expired knowledge")
    require(any(item["status"] == "conflicted" for item in knowledge), "missing conflicted knowledge")
    require(len(eval_cases) == 150, f"expected 150 eval cases, got {len(eval_cases)}")
    require(len({item["eval_id"] for item in eval_cases}) == len(eval_cases), "duplicate eval_id")
    require(sum(1 for item in eval_cases if item["severity"] == "release_blocker") >= 50, "release blockers underrepresented")

    return {
        "ok": not errors,
        "errors": errors,
        "counts": {
            "organizations": len(orgs),
            "users": len(users),
            "memberships": len(memberships),
            "assignments": len(assignments),
            "cases": len(cases),
            "case_events": len(case_events),
            "tickets": len(tickets),
            "ticket_events": len(ticket_events),
            "knowledge_documents": len(knowledge),
            "eval_cases": len(eval_cases),
        },
    }


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
