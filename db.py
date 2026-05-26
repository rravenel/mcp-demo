import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "data/delivery.db")

DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('active', 'at_risk')),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    name       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('active', 'at_risk', 'complete')),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS milestones (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name       TEXT NOT NULL,
    "order"    INTEGER NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('not_started', 'in_progress', 'complete')),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    milestone_id TEXT NOT NULL REFERENCES milestones(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'pending_customer', 'blocked', 'complete', 'invalid')),
    owner        TEXT,
    blocker      TEXT,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_account_id   ON projects(account_id);
CREATE INDEX IF NOT EXISTS idx_milestones_project_id ON milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone_id    ON tasks(milestone_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


def fetch_account(conn: sqlite3.Connection, account_id: str):
    return conn.execute(
        "SELECT id, name, status, updated_at FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()


def fetch_active_project(conn: sqlite3.Connection, account_id: str):
    return conn.execute(
        "SELECT id, name, status FROM projects WHERE account_id = ? AND status != 'complete' LIMIT 1",
        (account_id,),
    ).fetchone()


def fetch_current_milestone(conn: sqlite3.Connection, project_id: str):
    row = conn.execute(
        "SELECT id, name, status FROM milestones WHERE project_id = ? AND status = 'in_progress' LIMIT 1",
        (project_id,),
    ).fetchone()
    if row:
        return row
    return conn.execute(
        'SELECT id, name, status FROM milestones WHERE project_id = ? AND status = \'not_started\' ORDER BY "order" ASC LIMIT 1',
        (project_id,),
    ).fetchone()


def fetch_tasks_for_milestone(conn: sqlite3.Connection, milestone_id: str):
    return conn.execute(
        "SELECT id, title, status, owner, blocker, updated_at FROM tasks WHERE milestone_id = ? ORDER BY rowid",
        (milestone_id,),
    ).fetchall()


def fetch_task(conn: sqlite3.Connection, task_id: str):
    return conn.execute(
        "SELECT id, title, status, owner, blocker, updated_at FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()


def update_task(conn: sqlite3.Connection, task_id: str, new_status: str, now: str) -> None:
    conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now, task_id),
    )


def fetch_incomplete_tasks_for_milestone(conn: sqlite3.Connection, milestone_id: str):
    return conn.execute(
        "SELECT id, title, status, blocker FROM tasks WHERE milestone_id = ? AND status != 'complete' ORDER BY rowid",
        (milestone_id,),
    ).fetchall()


def fetch_milestone_for_task(conn: sqlite3.Connection, task_id: str):
    return conn.execute(
        """
        SELECT m.id, m.project_id, m.name, m.status
        FROM milestones m
        JOIN tasks t ON t.milestone_id = m.id
        WHERE t.id = ?
        """,
        (task_id,),
    ).fetchone()


def complete_milestone(conn: sqlite3.Connection, milestone_id: str, now: str) -> None:
    conn.execute(
        "UPDATE milestones SET status = 'complete', updated_at = ? WHERE id = ?",
        (now, milestone_id),
    )


def fetch_incomplete_milestones_for_project(conn: sqlite3.Connection, project_id: str):
    return conn.execute(
        'SELECT id, name, status FROM milestones WHERE project_id = ? AND status != \'complete\' ORDER BY "order"',
        (project_id,),
    ).fetchall()


def fetch_project_for_milestone(conn: sqlite3.Connection, milestone_id: str):
    return conn.execute(
        """
        SELECT p.id, p.account_id, p.name, p.status
        FROM projects p
        JOIN milestones m ON m.project_id = p.id
        WHERE m.id = ?
        """,
        (milestone_id,),
    ).fetchone()


def complete_project(conn: sqlite3.Connection, project_id: str, now: str) -> None:
    conn.execute(
        "UPDATE projects SET status = 'complete', updated_at = ? WHERE id = ?",
        (now, project_id),
    )


def clear_account_at_risk(conn: sqlite3.Connection, account_id: str, now: str) -> None:
    conn.execute(
        "UPDATE accounts SET status = 'active', updated_at = ? WHERE id = ? AND status = 'at_risk'",
        (now, account_id),
    )


def fetch_all_accounts_with_context(conn: sqlite3.Connection) -> list:
    accounts = conn.execute(
        "SELECT id, name, status, updated_at FROM accounts ORDER BY name"
    ).fetchall()

    result = []
    for acct in accounts:
        project_row = fetch_active_project(conn, acct["id"])
        project = None
        if project_row:
            milestone_row = fetch_current_milestone(conn, project_row["id"])
            milestone = None
            if milestone_row:
                task_rows = fetch_tasks_for_milestone(conn, milestone_row["id"])
                tasks = [
                    {
                        "id": t["id"],
                        "title": t["title"],
                        "status": t["status"],
                        "owner": t["owner"],
                        "blocker": t["blocker"],
                        "updated_at": t["updated_at"],
                    }
                    for t in task_rows
                ]
                milestone = {
                    "name": milestone_row["name"],
                    "status": milestone_row["status"],
                    "tasks": tasks,
                }
            project = {
                "name": project_row["name"],
                "status": project_row["status"],
                "milestone": milestone,
            }
        result.append(
            {
                "id": acct["id"],
                "name": acct["name"],
                "status": acct["status"],
                "updated_at": acct["updated_at"],
                "project": project,
            }
        )
    return result
