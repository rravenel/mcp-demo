from unittest.mock import patch

import json

import demo
from db import TaskStatus


# ---------------------------------------------------------------------------
# verify_update
# ---------------------------------------------------------------------------


def test_verify_update_returns_true_when_status_changed():
    with patch.object(demo, "call_tool", return_value=json.dumps({"status": "pending_customer"})):
        assert demo.verify_update("t1", TaskStatus.BLOCKED) is True


def test_verify_update_returns_false_when_status_unchanged():
    with patch.object(demo, "call_tool", return_value=json.dumps({"status": "blocked"})):
        assert demo.verify_update("t1", TaskStatus.BLOCKED) is False


# ---------------------------------------------------------------------------
# Data extraction from resource response
# ---------------------------------------------------------------------------

_RESOURCE_DATA = [
    {
        "text": '[{"id": "acme", "name": "Acme Corp", "status": "active", "updated_at": "2024-01-01T00:00:00Z", "project": {"name": "Acme Project", "status": "active", "milestone": {"name": "M1", "status": "in_progress", "tasks": [{"id": "acme-t1", "title": "T1", "status": "complete", "owner": null, "blocker": null, "updated_at": "2024-01-01T00:00:00Z"}]}}}, {"id": "globex", "name": "Globex Inc", "status": "at_risk", "updated_at": "2024-01-01T00:00:00Z", "project": {"name": "Globex Project", "status": "at_risk", "milestone": {"name": "M2", "status": "in_progress", "tasks": [{"id": "globex-t1", "title": "T1", "status": "complete", "owner": null, "blocker": null, "updated_at": "2024-01-01T00:00:00Z"}, {"id": "globex-t2", "title": "T2", "status": "blocked", "owner": "Eve", "blocker": "Waiting", "updated_at": "2024-01-01T00:00:00Z"}]}}}]'
    }
]


def test_globex_id_extraction():
    accounts = demo._parse_accounts(_RESOURCE_DATA)
    globex = next(a for a in accounts if a["name"] == "Globex Inc")
    assert globex["id"] == "globex"


def test_blocked_task_id_extraction():
    accounts = demo._parse_accounts(_RESOURCE_DATA)
    globex = next(a for a in accounts if a["name"] == "Globex Inc")
    tasks = globex["project"]["milestone"]["tasks"]
    blocked = next(t for t in tasks if t["status"] == "blocked")
    assert blocked["id"] == "globex-t2"
