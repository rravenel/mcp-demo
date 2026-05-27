"""Seed script — populates data/delivery.db with demo data. Not application code."""

import os
import sqlite3
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get("DB_PATH", "data/delivery.db")


def ts(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('active', 'at_risk')),
    updated_at DATETIME NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    name       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('active', 'at_risk', 'complete')),
    updated_at DATETIME NOT NULL
);
CREATE TABLE IF NOT EXISTS milestones (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name       TEXT NOT NULL,
    "order"    INTEGER NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('not_started', 'in_progress', 'complete')),
    updated_at DATETIME NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    milestone_id TEXT NOT NULL REFERENCES milestones(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'pending_customer', 'blocked', 'complete', 'invalid')),
    owner        TEXT,
    blocker      TEXT,
    updated_at   DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_account_id   ON projects(account_id);
CREATE INDEX IF NOT EXISTS idx_milestones_project_id ON milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone_id    ON tasks(milestone_id);
"""

SEED = [
    # Acme Corp — active account
    ("INSERT OR REPLACE INTO accounts VALUES (?,?,?,?)", ("acme", "Acme Corp", "active", ts())),
    (
        "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?)",
        ("acme-proj", "acme", "Acme Onboarding", "active", ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("acme-m1", "acme-proj", "Kickoff & Setup", 1, "complete", ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("acme-m2", "acme-proj", "Integration & Testing", 2, "in_progress", ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("acme-t1", "acme-m2", "Configure SSO", "complete", "Alice", None, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("acme-t2", "acme-m2", "Run smoke tests", "complete", "Bob", None, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("acme-t3", "acme-m2", "UAT sign-off", "open", "Carol", None, ts()),
    ),
    # Globex Inc — at_risk account
    ("INSERT OR REPLACE INTO accounts VALUES (?,?,?,?)", ("globex", "Globex Inc", "at_risk", ts())),
    (
        "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?)",
        ("globex-proj", "globex", "Globex Onboarding", "at_risk", ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("globex-m1", "globex-proj", "Kickoff & Setup", 1, "complete", ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("globex-m2", "globex-proj", "Integration & Testing", 2, "in_progress", ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("globex-t1", "globex-m2", "Configure SSO", "complete", "Dave", None, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        (
            "globex-t2",
            "globex-m2",
            "Customer data migration sign-off",
            "blocked",
            "Eve",
            "Customer has not submitted the required compliance document",
            ts(14),
        ),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("globex-t3", "globex-m2", "Legacy API decommission", "invalid", None, None, ts()),
    ),
]


def main():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = ON")
    for stmt in (s.strip() for s in DDL.split(";") if s.strip()):
        conn.execute(stmt)
    for sql, params in SEED:
        conn.execute(sql, params)
    conn.close()
    print(f"Seeded {DB_PATH}")


if __name__ == "__main__":
    main()
