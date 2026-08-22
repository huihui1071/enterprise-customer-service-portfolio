import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DATABASE_PATH, DATA_ROOT


SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    organization_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    membership_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    data TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id)
);
CREATE TABLE IF NOT EXISTS assignments (
    assignment_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    assistant_user_id TEXT NOT NULL,
    doctor_user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    data TEXT NOT NULL,
    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id),
    FOREIGN KEY(assistant_user_id) REFERENCES users(user_id),
    FOREIGN KEY(doctor_user_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    primary_doctor_user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL,
    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id),
    FOREIGN KEY(primary_doctor_user_id) REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    reporter_user_id TEXT NOT NULL,
    assignee_user_id TEXT,
    case_id TEXT,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    data TEXT NOT NULL,
    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id),
    FOREIGN KEY(reporter_user_id) REFERENCES users(user_id),
    FOREIGN KEY(assignee_user_id) REFERENCES users(user_id),
    FOREIGN KEY(case_id) REFERENCES cases(case_id)
);
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    actor_user_id TEXT,
    action TEXT NOT NULL,
    object_type TEXT,
    object_id TEXT,
    result TEXT NOT NULL,
    internal_reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_membership_lookup ON memberships(user_id, organization_id, role, status);
CREATE INDEX IF NOT EXISTS idx_assignment_lookup ON assignments(assistant_user_id, doctor_user_id, organization_id, status);
CREATE INDEX IF NOT EXISTS idx_case_doctor ON cases(primary_doctor_user_id, organization_id);
"""


def _load(name):
    return json.loads((DATA_ROOT / "seed" / name).read_text(encoding="utf-8"))


@contextmanager
def connection():
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database(force=False):
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if force and DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    with connection() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        for item in _load("organizations.json"):
            conn.execute("INSERT INTO organizations VALUES (?, ?)", (item["organization_id"], json.dumps(item, ensure_ascii=False)))
        for item in _load("users.json"):
            conn.execute("INSERT INTO users VALUES (?, ?)", (item["user_id"], json.dumps(item, ensure_ascii=False)))
        for item in _load("memberships.json"):
            conn.execute(
                "INSERT INTO memberships VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item["membership_id"], item["user_id"], item["organization_id"], item["role"], item["status"], item["valid_from"], item["valid_to"], json.dumps(item, ensure_ascii=False)),
            )
        for item in _load("assistant_doctor_assignments.json"):
            conn.execute(
                "INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item["assignment_id"], item["organization_id"], item["assistant_user_id"], item["doctor_user_id"], item["status"], item["valid_from"], item["valid_to"], json.dumps(item, ensure_ascii=False)),
            )
        for item in _load("cases.json"):
            conn.execute(
                "INSERT INTO cases VALUES (?, ?, ?, ?, ?)",
                (item["case_id"], item["organization_id"], item["primary_doctor_user_id"], item["status"], json.dumps(item, ensure_ascii=False)),
            )
        for item in _load("tickets.json"):
            request_hash = f"seed:{item['ticket_id']}"
            conn.execute(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item["ticket_id"], item["organization_id"], item["reporter_user_id"], item["assignee_user_id"], item["case_id"], item["status"], item["idempotency_key"], request_hash, json.dumps(item, ensure_ascii=False)),
            )


def decode_row(row):
    return json.loads(row["data"]) if row else None


def audit(conn, trace_id, actor_user_id, action, object_type, object_id, result, internal_reason=None):
    conn.execute(
        "INSERT INTO audit_logs(trace_id, actor_user_id, action, object_type, object_id, result, internal_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (trace_id, actor_user_id, action, object_type, object_id, result, internal_reason, datetime.now(timezone.utc).isoformat()),
    )
    # Security denials must survive the application exception raised immediately after logging.
    conn.commit()
