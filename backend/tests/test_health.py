"""Phase 0 tests — /health and /api/version endpoints.

Uses FastAPI's TestClient (synchronous httpx wrapper).
No database connection is required: neither endpoint touches the DB.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.version import __version__

client = TestClient(app)


def test_health_returns_ok() -> None:
    """GET /health → 200 {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_version() -> None:
    """GET /api/version → 200 {"version": "<current>"}."""
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == __version__
    assert __version__ == "0.1.0"


def test_openapi_schema_accessible() -> None:
    """OpenAPI schema endpoint is reachable (confirms FastAPI wiring)."""
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "PartFolder 3D"
