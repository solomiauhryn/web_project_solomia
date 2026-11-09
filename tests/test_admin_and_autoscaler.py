from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.core.database import get_session, seed_default_admin
from app.main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_session():
    with Session(test_engine) as session:
        yield session


def test_admin_monitoring_and_autoscaler_limits():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        seed_default_admin(session)

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    ui_resp = client.get("/")
    assert ui_resp.status_code == 200
    assert "Розподілена система обернення матриць" in ui_resp.text

    login_resp = client.post(
        "/api/auth/login",
        json={
            "username": settings.FIRST_ADMIN_USERNAME,
            "password": settings.FIRST_ADMIN_PASSWORD,
        },
    )
    assert login_resp.status_code == 200
    admin_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    overview = client.get("/api/admin/overview", headers=headers)
    assert overview.status_code == 200
    ov_data = overview.json()
    assert "system_metrics" in ov_data
    assert ov_data["autoscaler"]["max_workers"] == settings.MAX_WORKERS
    assert len(ov_data["backend_nodes"]) >= 2

    scale_ok = client.post(
        "/api/admin/workers/scale",
        json={"target_workers": 3, "auto_scale_enabled": False},
        headers=headers,
    )
    assert scale_ok.status_code == 200
    assert scale_ok.json()["current_workers"] == 3

    scale_exceed = client.post(
        "/api/admin/workers/scale",
        json={"target_workers": settings.MAX_WORKERS + 1},
        headers=headers,
    )
    assert scale_exceed.status_code == 400

    app.dependency_overrides.clear()
