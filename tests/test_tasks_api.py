from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.database import get_session
from app.main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_session():
    with Session(test_engine) as session:
        yield session


def test_task_lifecycle_quotas_and_complexity_limits():
    SQLModel.metadata.create_all(test_engine)
    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    reg = client.post(
        "/api/auth/register",
        json={
            "username": "matrix_user",
            "email": "matrix_user@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    too_large = client.post(
        "/api/tasks",
        json={"matrix_size": 950, "generate_random": True},
        headers=headers,
    )
    assert too_large.status_code == 422

    sync_task = client.post(
        "/api/tasks",
        json={
            "matrix_size": 4,
            "generate_random": False,
            "input_matrix": [
                [4.0, 1.0, 0.0, 0.0],
                [1.0, 4.0, 1.0, 0.0],
                [0.0, 1.0, 4.0, 1.0],
                [0.0, 0.0, 1.0, 4.0],
            ],
            "execute_immediately": True,
        },
        headers=headers,
    )
    assert sync_task.status_code == 201
    sync_data = sync_task.json()
    assert sync_data["status"] == "COMPLETED"
    assert sync_data["progress"] == 100

    res_resp = client.get(f"/api/tasks/{sync_data['id']}/result", headers=headers)
    assert res_resp.status_code == 200
    assert len(res_resp.json()["inverse_matrix"]) == 4

    q1 = client.post(
        "/api/tasks",
        json={"matrix_size": 50, "generate_random": True},
        headers=headers,
    )
    assert q1.status_code == 201
    assert q1.json()["status"] == "QUEUED"
    assert q1.json()["queue_position"] == 1
    assert q1.json()["estimated_wait_sec"] > 0

    q2 = client.post(
        "/api/tasks",
        json={"matrix_size": 60, "generate_random": True},
        headers=headers,
    )
    assert q2.status_code == 201
    assert q2.json()["queue_position"] == 2

    q3_overflow = client.post(
        "/api/tasks",
        json={"matrix_size": 30, "generate_random": True},
        headers=headers,
    )
    assert q3_overflow.status_code == 429

    cancel_resp = client.post(f"/api/tasks/{q1.json()['id']}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    hist_resp = client.get("/api/tasks", headers=headers)
    assert hist_resp.status_code == 200
    assert hist_resp.json()["total"] == 3
    assert hist_resp.json()["active_count"] == 1

    del_resp = client.delete(f"/api/tasks/{q1.json()['id']}", headers=headers)
    assert del_resp.status_code == 204

    app.dependency_overrides.clear()
