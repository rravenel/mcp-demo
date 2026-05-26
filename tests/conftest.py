import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

import db


def _ts(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class _NoClose:
    """Proxy that delegates all attribute access to a connection but ignores close().

    Used in test monkeypatching so that handler code calling conn.close() does
    not invalidate the shared fixture connection.
    """

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    db.apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db_conn(db_conn):
    conn = db_conn
    now = _ts()
    past = _ts(14)

    # Acme Corp — active account
    conn.execute("INSERT INTO accounts VALUES ('acme', 'Acme Corp', 'active', ?)", (now,))
    conn.execute("INSERT INTO projects VALUES ('acme-proj', 'acme', 'Acme Project', 'active', ?)", (now,))
    conn.execute("INSERT INTO milestones VALUES ('acme-m1', 'acme-proj', 'Milestone 1', 1, 'complete', ?)", (now,))
    conn.execute("INSERT INTO milestones VALUES ('acme-m2', 'acme-proj', 'Milestone 2', 2, 'in_progress', ?)", (now,))
    conn.execute("INSERT INTO tasks VALUES ('acme-t1', 'acme-m2', 'Task 1', 'complete', 'Alice', NULL, ?)", (now,))
    conn.execute("INSERT INTO tasks VALUES ('acme-t2', 'acme-m2', 'Task 2', 'complete', 'Bob', NULL, ?)", (now,))
    conn.execute("INSERT INTO tasks VALUES ('acme-t3', 'acme-m2', 'Task 3', 'open', 'Carol', NULL, ?)", (now,))

    # Globex Inc — at_risk account
    conn.execute("INSERT INTO accounts VALUES ('globex', 'Globex Inc', 'at_risk', ?)", (now,))
    conn.execute("INSERT INTO projects VALUES ('globex-proj', 'globex', 'Globex Project', 'at_risk', ?)", (now,))
    conn.execute("INSERT INTO milestones VALUES ('globex-m1', 'globex-proj', 'Milestone 1', 1, 'complete', ?)", (now,))
    conn.execute("INSERT INTO milestones VALUES ('globex-m2', 'globex-proj', 'Milestone 2', 2, 'in_progress', ?)", (now,))
    conn.execute("INSERT INTO tasks VALUES ('globex-t1', 'globex-m2', 'Task 1', 'complete', 'Dave', NULL, ?)", (now,))
    conn.execute("INSERT INTO tasks VALUES ('globex-t2', 'globex-m2', 'Task 2', 'blocked', 'Eve', 'Waiting on customer sign-off', ?)", (past,))
    conn.execute("INSERT INTO tasks VALUES ('globex-t3', 'globex-m2', 'Task 3', 'invalid', NULL, NULL, ?)", (now,))

    yield conn
