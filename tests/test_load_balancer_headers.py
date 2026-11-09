from fastapi.testclient import TestClient
from app.main import app


def test_cluster_node_and_load_balancer_headers():
    client = TestClient(app)
    resp = client.get(
        "/api/cluster/node",
        headers={
            "X-Forwarded-For": "192.168.1.10",
            "X-Forwarded-Proto": "https",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "instance_hostname" in data
    assert data["forwarded_proto"] == "https"
    assert resp.headers.get("X-Served-By") == data["instance_hostname"]
