from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_current_admin
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


def test_register_login_and_role_guards():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        seed_default_admin(session)

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    reg_resp = client.post(
        "/api/auth/register",
        json={
            "username": "solomia",
            "email": "solomia@example.com",
            "password": "securepassword123",
        },
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["username"] == "solomia"
    assert reg_data["user"]["role"] == "user"
    user_token = reg_data["access_token"]

    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "solomia@example.com"

    dup_resp = client.post(
        "/api/auth/register",
        json={
            "username": "solomia",
            "email": "solomia@example.com",
            "password": "securepassword123",
        },
    )
    assert dup_resp.status_code == 400

    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": settings.FIRST_ADMIN_USERNAME,
            "password": settings.FIRST_ADMIN_PASSWORD,
        },
    )
    assert admin_login.status_code == 200
    admin_data = admin_login.json()
    assert admin_data["user"]["role"] == "admin"

    app.dependency_overrides.clear()
