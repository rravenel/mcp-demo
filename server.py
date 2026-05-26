import fastmcp
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = fastmcp.FastMCP("delivery-manager")


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
