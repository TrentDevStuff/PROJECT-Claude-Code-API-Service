"""Basic tests for API endpoints"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Claude Code API Service"
    assert data["version"] == "0.1.0"
    assert "docs" in data
    assert "health" in data


def test_health():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["version"] == "0.1.0"
    assert "services" in data


def test_docs_available():
    """Test that OpenAPI docs are available"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema():
    """Test that OpenAPI schema is available"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Claude Code API Service"
    assert schema["info"]["version"] == "0.1.0"
