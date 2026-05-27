from datetime import datetime, timezone, timedelta

import db


def _ts(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# fetch_account
# ---------------------------------------------------------------------------


def test_fetch_account_found(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    row = db.fetch_account(db_conn, "a1")
    assert row is not None
    assert row["id"] == "a1"
    assert row["name"] == "Acme"


def test_fetch_account_not_found(db_conn):
    assert db.fetch_account(db_conn, "missing") is None


# ---------------------------------------------------------------------------
# fetch_current_project
# ---------------------------------------------------------------------------


def test_fetch_current_project_found(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    row = db.fetch_current_project(db_conn, "a1")
    assert row is not None
    assert row["id"] == "p1"


def test_fetch_current_project_complete_excluded(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'complete', ?)", (now,))
    assert db.fetch_current_project(db_conn, "a1") is None


# ---------------------------------------------------------------------------
# fetch_current_milestone
# ---------------------------------------------------------------------------


def test_fetch_current_milestone_in_progress(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    row = db.fetch_current_milestone(db_conn, "p1")
    assert row["id"] == "m1"
    assert row["status"] == "in_progress"


def test_fetch_current_milestone_in_progress_over_not_started(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'not_started', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m2', 'p1', 'M2', 2, 'in_progress', ?)", (now,))
    row = db.fetch_current_milestone(db_conn, "p1")
    assert row["id"] == "m2"


def test_fetch_current_milestone_lowest_not_started(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 2, 'not_started', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m2', 'p1', 'M2', 1, 'not_started', ?)", (now,))
    row = db.fetch_current_milestone(db_conn, "p1")
    assert row["id"] == "m2"  # order=1


def test_fetch_current_milestone_all_complete(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'complete', ?)", (now,))
    assert db.fetch_current_milestone(db_conn, "p1") is None


# ---------------------------------------------------------------------------
# fetch_tasks_for_milestone
# ---------------------------------------------------------------------------


def test_fetch_tasks_for_milestone_with_tasks(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', NULL, NULL, ?)", (now,)
    )
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t2', 'm1', 'Task 2', 'complete', NULL, NULL, ?)", (now,)
    )
    rows = db.fetch_tasks_for_milestone(db_conn, "m1")
    assert len(rows) == 2
    assert rows[0]["id"] == "t1"
    assert rows[1]["id"] == "t2"


def test_fetch_tasks_for_milestone_empty(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    assert db.fetch_tasks_for_milestone(db_conn, "m1") == []


# ---------------------------------------------------------------------------
# fetch_task
# ---------------------------------------------------------------------------


def test_fetch_task_found(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', 'Alice', 'some blocker', ?)",
        (now,),
    )
    row = db.fetch_task(db_conn, "t1")
    assert row is not None
    assert row["id"] == "t1"
    assert row["title"] == "Task 1"
    assert row["owner"] == "Alice"
    assert row["blocker"] == "some blocker"


def test_fetch_task_not_found(db_conn):
    assert db.fetch_task(db_conn, "missing") is None


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------


def test_update_task(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', 'Alice', 'blocker', ?)", (now,)
    )
    new_ts = _ts()
    db.update_task(db_conn, "t1", "complete", new_ts)
    row = db.fetch_task(db_conn, "t1")
    assert row["status"] == "complete"
    assert row["updated_at"] == new_ts
    assert row["title"] == "Task 1"
    assert row["owner"] == "Alice"
    assert row["blocker"] == "blocker"


# ---------------------------------------------------------------------------
# fetch_incomplete_tasks_for_milestone
# ---------------------------------------------------------------------------


def test_fetch_incomplete_tasks_excludes_complete(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'complete', NULL, NULL, ?)", (now,)
    )
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t2', 'm1', 'Task 2', 'blocked', NULL, 'b', ?)", (now,)
    )
    rows = db.fetch_incomplete_tasks_for_milestone(db_conn, "m1")
    ids = [r["id"] for r in rows]
    assert "t1" not in ids
    assert "t2" in ids


def test_fetch_incomplete_tasks_includes_invalid(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'invalid', NULL, NULL, ?)", (now,)
    )
    rows = db.fetch_incomplete_tasks_for_milestone(db_conn, "m1")
    assert len(rows) == 1
    assert rows[0]["id"] == "t1"


def test_fetch_incomplete_tasks_empty_when_all_complete(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'complete', NULL, NULL, ?)", (now,)
    )
    assert db.fetch_incomplete_tasks_for_milestone(db_conn, "m1") == []


# ---------------------------------------------------------------------------
# fetch_milestone_for_task
# ---------------------------------------------------------------------------


def test_fetch_milestone_for_task(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', NULL, NULL, ?)", (now,)
    )
    row = db.fetch_milestone_for_task(db_conn, "t1")
    assert row["id"] == "m1"
    assert row["project_id"] == "p1"


# ---------------------------------------------------------------------------
# complete_milestone
# ---------------------------------------------------------------------------


def test_complete_milestone(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    new_ts = _ts()
    db.complete_milestone(db_conn, "m1", new_ts)
    row = db_conn.execute(
        "SELECT status, updated_at, name FROM milestones WHERE id = 'm1'"
    ).fetchone()
    assert row["status"] == "complete"
    assert row["updated_at"] == new_ts
    assert row["name"] == "M1"


# ---------------------------------------------------------------------------
# fetch_incomplete_milestones_for_project
# ---------------------------------------------------------------------------


def test_fetch_incomplete_milestones_excludes_complete(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'complete', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m2', 'p1', 'M2', 2, 'not_started', ?)", (now,))
    rows = db.fetch_incomplete_milestones_for_project(db_conn, "p1")
    ids = [r["id"] for r in rows]
    assert "m1" not in ids
    assert "m2" in ids


def test_fetch_incomplete_milestones_ordered_by_order(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 3, 'not_started', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m2', 'p1', 'M2', 1, 'in_progress', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m3', 'p1', 'M3', 2, 'not_started', ?)", (now,))
    rows = db.fetch_incomplete_milestones_for_project(db_conn, "p1")
    assert [r["id"] for r in rows] == ["m2", "m3", "m1"]


# ---------------------------------------------------------------------------
# fetch_project_for_milestone
# ---------------------------------------------------------------------------


def test_fetch_project_for_milestone(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    row = db.fetch_project_for_milestone(db_conn, "m1")
    assert row["id"] == "p1"
    assert row["account_id"] == "a1"


# ---------------------------------------------------------------------------
# complete_project
# ---------------------------------------------------------------------------


def test_complete_project(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    new_ts = _ts()
    db.complete_project(db_conn, "p1", new_ts)
    row = db_conn.execute(
        "SELECT status, updated_at, name FROM projects WHERE id = 'p1'"
    ).fetchone()
    assert row["status"] == "complete"
    assert row["updated_at"] == new_ts
    assert row["name"] == "Proj"


# ---------------------------------------------------------------------------
# clear_account_at_risk
# ---------------------------------------------------------------------------


def test_clear_account_at_risk(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'at_risk', ?)", (now,))
    new_ts = _ts()
    db.clear_account_at_risk(db_conn, "a1", new_ts)
    row = db_conn.execute("SELECT status, updated_at FROM accounts WHERE id = 'a1'").fetchone()
    assert row["status"] == "active"
    assert row["updated_at"] == new_ts


def test_clear_account_at_risk_no_op_when_active(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db.clear_account_at_risk(db_conn, "a1", _ts())
    row = db_conn.execute("SELECT status, updated_at FROM accounts WHERE id = 'a1'").fetchone()
    assert row["status"] == "active"
    assert row["updated_at"] == now


# ---------------------------------------------------------------------------
# fetch_all_accounts_with_context
# ---------------------------------------------------------------------------


def test_fetch_all_accounts_ordered_by_name(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('z', 'Zebra', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO accounts VALUES ('a', 'Aardvark', 'active', ?)", (now,))
    rows = db.fetch_all_accounts_with_context(db_conn)
    assert [r["name"] for r in rows] == ["Aardvark", "Zebra"]


def test_fetch_all_accounts_nested_structure(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    db_conn.execute(
        "INSERT INTO tasks VALUES ('t1', 'm1', 'Task 1', 'open', 'Alice', NULL, ?)", (now,)
    )
    rows = db.fetch_all_accounts_with_context(db_conn)
    assert len(rows) == 1
    acct = rows[0]
    assert acct["id"] == "a1"
    assert acct["project"]["name"] == "Proj"
    assert acct["project"]["milestone"]["name"] == "M1"
    assert len(acct["project"]["milestone"]["tasks"]) == 1
    assert acct["project"]["milestone"]["tasks"][0]["id"] == "t1"


def test_fetch_all_accounts_no_active_project(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'complete', ?)", (now,))
    rows = db.fetch_all_accounts_with_context(db_conn)
    assert rows[0]["project"] is None


def test_fetch_all_accounts_no_current_milestone(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'complete', ?)", (now,))
    rows = db.fetch_all_accounts_with_context(db_conn)
    assert rows[0]["project"]["milestone"] is None


def test_fetch_all_accounts_empty_tasks(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO milestones VALUES ('m1', 'p1', 'M1', 1, 'in_progress', ?)", (now,))
    rows = db.fetch_all_accounts_with_context(db_conn)
    assert rows[0]["project"]["milestone"]["tasks"] == []


def test_fetch_all_accounts_complete_project_excluded(db_conn):
    now = _ts()
    db_conn.execute("INSERT INTO accounts VALUES ('a1', 'Acme', 'active', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p1', 'a1', 'Proj 1', 'complete', ?)", (now,))
    db_conn.execute("INSERT INTO projects VALUES ('p2', 'a1', 'Proj 2', 'active', ?)", (now,))
    rows = db.fetch_all_accounts_with_context(db_conn)
    assert rows[0]["project"]["name"] == "Proj 2"
