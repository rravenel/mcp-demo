"""Seed script — populates data/delivery.db with demo data. Not application code."""

import os
import sqlite3
from datetime import datetime, timezone, timedelta

from db import DDL, AccountStatus, MilestoneStatus, ProjectStatus, TaskStatus

DB_PATH = os.environ.get("DB_PATH", "data/delivery.db")


def ts(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


SEED = [
    # Acme Corp — active account
    ("INSERT OR REPLACE INTO accounts VALUES (?,?,?,?)", ("acme", "Acme Corp", AccountStatus.ACTIVE, ts())),
    (
        "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?)",
        ("acme-proj", "acme", "Acme Onboarding", ProjectStatus.ACTIVE, ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("acme-m1", "acme-proj", "Kickoff & Setup", 1, MilestoneStatus.COMPLETE, ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("acme-m2", "acme-proj", "Integration & Testing", 2, MilestoneStatus.IN_PROGRESS, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("acme-t1", "acme-m2", "Configure SSO", TaskStatus.COMPLETE, "Alice", None, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("acme-t2", "acme-m2", "Run smoke tests", TaskStatus.COMPLETE, "Bob", None, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("acme-t3", "acme-m2", "UAT sign-off", TaskStatus.OPEN, "Carol", None, ts()),
    ),
    # Globex Inc — at_risk account
    ("INSERT OR REPLACE INTO accounts VALUES (?,?,?,?)", ("globex", "Globex Inc", AccountStatus.AT_RISK, ts())),
    (
        "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?)",
        ("globex-proj", "globex", "Globex Onboarding", ProjectStatus.AT_RISK, ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("globex-m1", "globex-proj", "Kickoff & Setup", 1, MilestoneStatus.COMPLETE, ts()),
    ),
    (
        "INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
        ("globex-m2", "globex-proj", "Integration & Testing", 2, MilestoneStatus.IN_PROGRESS, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("globex-t1", "globex-m2", "Configure SSO", TaskStatus.COMPLETE, "Dave", None, ts()),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        (
            "globex-t2",
            "globex-m2",
            "Customer data migration sign-off",
            TaskStatus.BLOCKED,
            "Eve",
            "Customer has not submitted the required compliance document",
            ts(14),
        ),
    ),
    (
        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)",
        ("globex-t3", "globex-m2", "Legacy API decommission", TaskStatus.INVALID, None, None, ts()),
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
