import pytest

import db
import server


@pytest.fixture(autouse=True)
def patch_db(seeded_db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: seeded_db_conn)


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
    monkeypatch.setattr(db, "get_connection", lambda: db_conn)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'complete', ?)", (now,))
    result = server.get_account_status("a1")
    assert result["error"] is True
    assert result["code"] == "NO_ACTIVE_PROJECT"


def test_get_account_status_no_current_milestone(db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: db_conn)
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
