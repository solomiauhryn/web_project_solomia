from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.database import get_session
from app.main import app
from app.models.task import MatrixTask, TaskStatus
from app.models.user import User, UserRole

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_session():
    with Session(test_engine) as session:
        yield session


def test_health_endpoint_and_models():
    SQLModel.metadata.create_all(test_engine)
    app.dependency_overrides[get_session] = override_get_session

    with Session(test_engine) as session:
        user = User(
            username="student",
            email="student@example.com",
            hashed_password="hashed_password_placeholder",
            role=UserRole.USER,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        task = MatrixTask(
            user_id=user.id,
            matrix_size=100,
            status=TaskStatus.QUEUED,
            progress=0,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        assert task.id is not None
        assert task.status == TaskStatus.QUEUED

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "healthy"
    assert "instance_hostname" in data
    assert "X-Served-By" in response.headers

    app.dependency_overrides.clear()
