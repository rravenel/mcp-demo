import pytest

import db
import mcp_demo_server as server
from tests.conftest import _NoClose


@pytest.fixture(autouse=True)
def patch_db(seeded_db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(seeded_db_conn))


# ---------------------------------------------------------------------------
# get_account_status
# ---------------------------------------------------------------------------


def test_get_account_status_success(seeded_db_conn):
    result = server.get_account_status("acme")
    assert "error" not in result
    assert result["account"]["id"] == "acme"
    assert result["account"]["name"] == "Acme Corp"
    assert result["project"]["id"] == "acme-proj"
    assert result["milestone"]["id"] == "acme-m2"
    tasks = result["tasks"]
    assert len(tasks) == 3
    for t in tasks:
        for field in ("id", "title", "status", "owner", "blocker", "updated_at"):
            assert field in t


def test_get_account_status_not_found(seeded_db_conn):
    result = server.get_account_status("missing")
    assert result["error"] is True
    assert result["code"] == "ACCOUNT_NOT_FOUND"


def test_get_account_status_no_active_project(db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(db_conn))
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'complete', ?)", (now,))
    result = server.get_account_status("a1")
    assert result["error"] is True
    assert result["code"] == "NO_ACTIVE_PROJECT"


def test_get_account_status_no_current_milestone(db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(db_conn))
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'complete', ?)", (now,))
    result = server.get_account_status("a1")
    assert result["error"] is True
    assert result["code"] == "NO_CURRENT_MILESTONE"


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------


def test_get_task_success(seeded_db_conn):
    result = server.get_task("globex-t2")
    assert "error" not in result
    assert result["id"] == "globex-t2"
    for field in ("id", "title", "status", "owner", "blocker", "updated_at"):
        assert field in result


def test_get_task_not_found(seeded_db_conn):
    result = server.get_task("missing")
    assert result["error"] is True
    assert result["code"] == "TASK_NOT_FOUND"


# ---------------------------------------------------------------------------
# update_task_status
# ---------------------------------------------------------------------------


def test_update_task_invalid_status(seeded_db_conn):
    result = server.update_task_status("acme-t3", "flying")
    assert result["error"] is True
    assert result["code"] == "INVALID_STATUS"
    assert result["current_status"] == "open"


def test_update_task_invalid_status_db_unchanged(seeded_db_conn):
    server.update_task_status("acme-t3", "flying")
    row = seeded_db_conn.execute("SELECT status FROM tasks WHERE id = 'acme-t3'").fetchone()
    assert row["status"] == "open"


def test_update_task_not_found(seeded_db_conn):
    result = server.update_task_status("missing", "complete")
    assert result["error"] is True
    assert result["code"] == "TASK_NOT_FOUND"


def test_update_task_milestone_not_complete(seeded_db_conn):
    # Completing globex-t1 (already complete is wrong — use acme-t3 open task)
    # acme-m2 has t1 complete, t2 complete, t3 open — completing t3 would complete milestone
    # Use globex: complete globex-t1 is already complete; mark globex-t2 (blocked) -> pending_customer
    # globex-m2 still has globex-t3 (invalid) so milestone won't advance
    result = server.update_task_status("globex-t2", "pending_customer")
    assert "error" not in result
    assert result["task_updated"]["new_status"] == "pending_customer"
    assert result["milestone_advanced"] is False
    blocking = result["blocking_tasks"]
    ids = [t["id"] for t in blocking]
    assert "globex-t3" in ids   # invalid task blocks milestone
    assert "globex-t1" not in ids  # complete task excluded


def test_update_task_task_and_updated_at_persisted(seeded_db_conn):
    server.update_task_status("globex-t2", "pending_customer")
    row = seeded_db_conn.execute("SELECT status FROM tasks WHERE id = 'globex-t2'").fetchone()
    assert row["status"] == "pending_customer"


def test_update_task_milestone_advanced(db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(db_conn))
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m2', 'p1', 'M2', 2, 'not_started', ?)", (now,))
    db_conn.execute("INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', NULL, NULL, ?)", (now,))
    db_conn.execute("INSERT INTO tasks VALUES ('t2', 'm2', 'Task 2', 'open', NULL, NULL, ?)", (now,))
    result = server.update_task_status("t1", "complete")
    assert result["milestone_advanced"] is True
    m1_row = db_conn.execute("SELECT status FROM milestones WHERE id = 'm1'").fetchone()
    assert m1_row["status"] == "complete"
    remaining = result["remaining_milestones"]
    assert any(m["id"] == "m2" for m in remaining)


def test_update_task_full_cascade(db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(db_conn))
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'at_risk', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'at_risk', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute("INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', NULL, NULL, ?)", (now,))
    result = server.update_task_status("t1", "complete")
    assert result["project_complete"] is True
    assert result["account_status_updated"] is True
    project_row = db_conn.execute("SELECT status FROM projects WHERE id = 'p1'").fetchone()
    assert project_row["status"] == "complete"
    account_row = db_conn.execute("SELECT status FROM accounts WHERE id = 'a1'").fetchone()
    assert account_row["status"] == "active"
