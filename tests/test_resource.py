import pytest

import db
import server
from tests.conftest import _NoClose


@pytest.fixture(autouse=True)
def patch_db(seeded_db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(seeded_db_conn))


def test_resource_returns_both_accounts(seeded_db_conn):
    result = server.accounts_all()
    assert len(result) == 2


def test_resource_ordered_by_name(seeded_db_conn):
    result = server.accounts_all()
    assert result[0]["name"] == "Acme Corp"
    assert result[1]["name"] == "Globex Inc"


def test_resource_account_fields(seeded_db_conn):
    result = server.accounts_all()
    acme = result[0]
    for field in ("id", "name", "status", "updated_at"):
        assert field in acme


def test_resource_project_fields(seeded_db_conn):
    result = server.accounts_all()
    project = result[0]["project"]
    assert "name" in project
    assert "status" in project


def test_resource_milestone_fields(seeded_db_conn):
    result = server.accounts_all()
    milestone = result[0]["project"]["milestone"]
    assert "name" in milestone
    assert "status" in milestone


def test_resource_task_fields(seeded_db_conn):
    result = server.accounts_all()
    task = result[0]["project"]["milestone"]["tasks"][0]
    for field in ("id", "title", "status", "owner", "blocker", "updated_at"):
        assert field in task


def test_resource_globex_milestone2_tasks(seeded_db_conn):
    result = server.accounts_all()
    globex = next(a for a in result if a["name"] == "Globex Inc")
    tasks = globex["project"]["milestone"]["tasks"]
    statuses = {t["status"] for t in tasks}
    assert "blocked" in statuses
    assert "complete" in statuses
    assert "invalid" in statuses
