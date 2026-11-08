import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models.task import MatrixTask, TaskStatus
from app.models.user import User, UserRole
from app.services.queue_estimator import get_queue_position_and_eta
from app.worker.matrix_math import (
    SingularMatrixError,
    TaskCancelledError,
    generate_invertible_matrix,
    invert_matrix_gauss_jordan,
)
from app.worker.tasks import execute_matrix_task_sync

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def test_gauss_jordan_inversion_and_singular_detection():
    mat = generate_invertible_matrix(8, seed=42)
    stages: list[tuple[int, str]] = []
    inv, res = invert_matrix_gauss_jordan(
        mat,
        progress_callback=lambda p, s: stages.append((p, s)),
    )
    assert len(inv) == 8
    assert res < 1e-6
    assert stages[-1][0] == 100

    singular = [
        [1.0, 2.0, 3.0],
        [2.0, 4.0, 6.0],
        [0.0, 1.0, 1.0],
    ]
    with pytest.raises(SingularMatrixError):
        invert_matrix_gauss_jordan(singular)

    with pytest.raises(TaskCancelledError):
        invert_matrix_gauss_jordan(mat, cancel_check=lambda: True)


def test_worker_execution_and_queue_eta():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        user = User(
            username="worker_tester",
            email="worker_tester@example.com",
            hashed_password="x",
            role=UserRole.USER,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        t1 = MatrixTask(
            user_id=user.id,
            matrix_size=120,
            status=TaskStatus.PROCESSING,
            progress=50,
        )
        t2 = MatrixTask(
            user_id=user.id,
            matrix_size=100,
            status=TaskStatus.QUEUED,
            progress=0,
        )
        t3 = MatrixTask(
            user_id=user.id,
            matrix_size=12,
            status=TaskStatus.QUEUED,
            progress=0,
        )
        session.add(t1)
        session.add(t2)
        session.add(t3)
        session.commit()
        session.refresh(t2)
        session.refresh(t3)

        pos2, eta2 = get_queue_position_and_eta(session, t2)
        pos3, eta3 = get_queue_position_and_eta(session, t3)
        assert pos2 == 1
        assert pos3 == 2
        assert eta3 > eta2

        t3_id = t3.id

    result = execute_matrix_task_sync(t3_id, db_engine=test_engine, worker_name="worker-1")
    assert result["status"] == TaskStatus.COMPLETED.value
    assert result["residual_norm"] < 1e-6
