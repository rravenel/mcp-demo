import fastmcp
from starlette.requests import Request
from starlette.responses import JSONResponse

import db

mcp = fastmcp.FastMCP("delivery-manager")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def get_account_status(account_id: str) -> dict:
    conn = db.get_connection()
    try:
        account = db.fetch_account(conn, account_id)
        if not account:
            return {"error": True, "code": "ACCOUNT_NOT_FOUND", "reason": f"No account with id '{account_id}'"}

        project = db.fetch_active_project(conn, account["id"])
        if not project:
            return {"error": True, "code": "NO_ACTIVE_PROJECT", "reason": f"No active project for account '{account_id}'"}

        milestone = db.fetch_current_milestone(conn, project["id"])
        if not milestone:
            return {"error": True, "code": "NO_CURRENT_MILESTONE", "reason": f"No current milestone for project '{project['id']}'"}

        tasks = db.fetch_tasks_for_milestone(conn, milestone["id"])
        return {
            "account":   {"id": account["id"], "name": account["name"], "status": account["status"], "updated_at": account["updated_at"]},
            "project":   {"id": project["id"], "name": project["name"], "status": project["status"]},
            "milestone": {"id": milestone["id"], "name": milestone["name"], "status": milestone["status"]},
            "tasks": [
                {"id": t["id"], "title": t["title"], "status": t["status"], "owner": t["owner"], "blocker": t["blocker"], "updated_at": t["updated_at"]}
                for t in tasks
            ],
        }
    finally:
        conn.close()


@mcp.tool()
def get_task(task_id: str) -> dict:
    conn = db.get_connection()
    try:
        task = db.fetch_task(conn, task_id)
        if not task:
            return {"error": True, "code": "TASK_NOT_FOUND", "reason": f"No task with id '{task_id}'"}
        return {"id": task["id"], "title": task["title"], "status": task["status"], "owner": task["owner"], "blocker": task["blocker"], "updated_at": task["updated_at"]}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
