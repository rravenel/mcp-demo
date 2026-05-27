from datetime import datetime, timezone

import fastmcp

from config import MCP_PORT
from fastmcp.prompts import Message
from starlette.requests import Request
from starlette.responses import JSONResponse

import db

mcp = fastmcp.FastMCP("delivery-manager")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def get_account_status(account_id: str) -> dict:
    if not account_id:
        return {
            "error": True,
            "code": "INVALID_ACCOUNT_ID",
            "reason": "account_id must not be empty",
        }
    conn = db.get_connection()
    try:
        account = db.fetch_account(conn, account_id)
        if not account:
            return {
                "error": True,
                "code": "ACCOUNT_NOT_FOUND",
                "reason": f"No account with id '{account_id}'",
            }

        project = db.fetch_current_project(conn, account["id"])
        if not project:
            return {
                "error": True,
                "code": "NO_CURRENT_PROJECT",
                "reason": f"No current project for account '{account_id}'",
            }

        milestone = db.fetch_current_milestone(conn, project["id"])
        if not milestone:
            return {
                "error": True,
                "code": "NO_CURRENT_MILESTONE",
                "reason": f"No current milestone for project '{project['id']}'",
            }

        tasks = db.fetch_tasks_for_milestone(conn, milestone["id"])
        return {
            "account": {
                "id": account["id"],
                "name": account["name"],
                "status": account["status"],
                "updated_at": account["updated_at"],
            },
            "project": {"id": project["id"], "name": project["name"], "status": project["status"]},
            "milestone": {
                "id": milestone["id"],
                "name": milestone["name"],
                "status": milestone["status"],
            },
            "tasks": [
                {
                    "id": t["id"],
                    "title": t["title"],
                    "status": t["status"],
                    "owner": t["owner"],
                    "blocker": t["blocker"],
                    "updated_at": t["updated_at"],
                }
                for t in tasks
            ],
        }
    finally:
        conn.close()


@mcp.tool()
def get_task(task_id: str) -> dict:
    if not task_id:
        return {
            "error": True,
            "code": "INVALID_TASK_ID",
            "reason": "task_id must not be empty",
        }
    conn = db.get_connection()
    try:
        task = db.fetch_task(conn, task_id)
        if not task:
            return {
                "error": True,
                "code": "TASK_NOT_FOUND",
                "reason": f"No task with id '{task_id}'",
            }
        return {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"],
            "owner": task["owner"],
            "blocker": task["blocker"],
            "updated_at": task["updated_at"],
        }
    finally:
        conn.close()


@mcp.resource("accounts://all")
def accounts_all() -> list:
    conn = db.get_connection()
    try:
        return db.fetch_all_accounts_with_context(conn)
    finally:
        conn.close()


@mcp.tool()
def update_task_status(task_id: str, new_status: str) -> dict:
    if not task_id:
        return {
            "error": True,
            "code": "INVALID_TASK_ID",
            "reason": "task_id must not be empty",
        }
    try:
        status = db.TaskStatus(new_status)
    except ValueError:
        return {
            "error": True,
            "code": "INVALID_STATUS",
            "reason": f"'{new_status}' is not a valid task status",
        }

    conn = db.get_connection()
    try:
        conn.execute("BEGIN")

        try:
            now = db.now()
            if not db.update_task(conn, task_id, status, now):
                conn.rollback()
                return {
                    "error": True,
                    "code": "TASK_NOT_FOUND",
                    "reason": f"No task with id '{task_id}'",
                }

            milestone = db.fetch_milestone_for_task(conn, task_id)
            milestone_id = milestone["id"]
            project_id = milestone["project_id"]

            incomplete_tasks = db.fetch_incomplete_tasks_for_milestone(conn, milestone_id)
            if incomplete_tasks:
                conn.commit()
                return {
                    "task_updated": {"id": task_id, "new_status": status},
                    "milestone_advanced": False,
                    "blocking_tasks": [
                        {
                            "id": t["id"],
                            "title": t["title"],
                            "status": t["status"],
                            "blocker": t["blocker"],
                        }
                        for t in incomplete_tasks
                    ],
                }

            db.complete_milestone(conn, milestone_id, now)

            project = db.fetch_project_for_milestone(conn, milestone_id)
            account_id = project["account_id"]

            incomplete_milestones = db.fetch_incomplete_milestones_for_project(conn, project_id)
            if incomplete_milestones:
                conn.commit()
                return {
                    "task_updated": {"id": task_id, "new_status": status},
                    "milestone_advanced": True,
                    "milestone": {
                        "id": milestone_id,
                        "name": milestone["name"],
                        "status": db.MilestoneStatus.COMPLETE,
                    },
                    "project_complete": False,
                    "remaining_milestones": [
                        {"id": m["id"], "name": m["name"], "status": m["status"]}
                        for m in incomplete_milestones
                    ],
                }

            db.complete_project(conn, project_id, now)
            db.clear_account_at_risk(conn, account_id, now)

            updated_account = db.fetch_account(conn, account_id)

            conn.commit()
            return {
                "task_updated": {"id": task_id, "new_status": status},
                "milestone_advanced": True,
                "milestone": {"id": milestone_id, "name": milestone["name"], "status": db.MilestoneStatus.COMPLETE},
                "project_complete": True,
                "project": {"id": project_id, "name": project["name"], "status": db.ProjectStatus.COMPLETE},
                "account_status_updated": True,
                "account": {
                    "id": account_id,
                    "name": updated_account["name"],
                    "status": updated_account["status"],
                },
            }
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


@mcp.prompt(name="assess-account")
def assess_account(account_id: str) -> list[Message]:
    status = get_account_status(account_id)
    if status.get("error"):
        raise ValueError(f"get_account_status error: {status.get('code')} — {status.get('reason')}")

    now = datetime.now(timezone.utc)
    blocked_tasks = [t for t in status["tasks"] if t["status"] == db.TaskStatus.BLOCKED]
    task_lines = []
    for t in blocked_tasks:
        updated = datetime.strptime(t["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        days_blocked = (now - updated).days
        task_lines.append(
            f"  - id: {t['id']}\n"
            f"    title: {t['title']}\n"
            f"    owner: {t['owner']}\n"
            f"    blocker: {t['blocker']}\n"
            f"    days_blocked: {days_blocked}"
        )

    blocked_section = "\n".join(task_lines) if task_lines else "  (none)"
    text = f"""## Account Briefing

Account: {status["account"]["name"]} (status: {status["account"]["status"]})
Project: {status["project"]["name"]} (status: {status["project"]["status"]})
Current Milestone: {status["milestone"]["name"]} (status: {status["milestone"]["status"]})

Blocked tasks:
{blocked_section}

## Instructions

This is a triage action. Your role is to move this blocked task forward by \
identifying who needs to act next. Do not mark tasks complete — resolving the \
underlying blocker requires confirmation outside this system and is handled \
separately.

For the blocked task listed above, call `update_task_status(task_id, new_status)` \
with one of the following:
- The blocker is on the customer's side → `new_status = "{db.TaskStatus.PENDING_CUSTOMER.value}"`
- The blocker is on our side and we can act → `new_status = "{db.TaskStatus.IN_PROGRESS.value}"`

The task must not remain `blocked`. Call `update_task_status` now.
"""
    return [Message(text)]


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=MCP_PORT)
