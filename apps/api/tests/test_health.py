from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200


def test_health_live_and_ready(client: TestClient) -> None:
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_docs_csp_allows_swagger_assets(client: TestClient) -> None:
    docs = client.get("/docs")
    assert docs.status_code == 200
    csp = docs.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp
    assert "unsafe-inline" in csp
    api = client.get("/health")
    assert "default-src 'none'" in api.headers["content-security-policy"]
