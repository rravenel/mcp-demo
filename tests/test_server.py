from starlette.testclient import TestClient

from server import mcp


def test_health():
    client = TestClient(mcp.http_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
