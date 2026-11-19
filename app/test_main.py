from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_healthz():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_version():
    res = client.get("/version")
    assert res.status_code == 200
    assert "version" in res.json()


def test_create_item_rejects_empty_name():
    res = client.post("/items", json={"name": "   "})
    assert res.status_code == 422


def test_metrics_endpoint():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text
