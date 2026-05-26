import pytest

import db
import mcp_demo_server as server
from tests.conftest import _NoClose


@pytest.fixture(autouse=True)
def patch_db(seeded_db_conn, monkeypatch):
    monkeypatch.setattr(db, "get_connection", lambda: _NoClose(seeded_db_conn))


def _text(result: list) -> str:
    return result[0]["content"]


def test_prompt_returns_user_message(seeded_db_conn):
    result = server.assess_account("globex")
    assert isinstance(result, list)
    assert result[0]["role"] == "user"


def test_prompt_contains_account_project_milestone(seeded_db_conn):
    text = _text(server.assess_account("globex"))
    assert "Globex Inc" in text
    assert "Globex Project" in text
    assert "Milestone 2" in text


def test_prompt_only_blocked_tasks_appear(seeded_db_conn):
    text = _text(server.assess_account("globex"))
    assert "globex-t2" in text
    assert "globex-t1" not in text
    assert "globex-t3" not in text
    assert "acme-t3" not in text


def test_prompt_days_blocked(seeded_db_conn):
    text = _text(server.assess_account("globex"))
    assert "days_blocked: 14" in text


def test_prompt_raises_for_unknown_account(seeded_db_conn):
    with pytest.raises(Exception):
        server.assess_account("missing")
