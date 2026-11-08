from datetime import datetime, timezone
import json
import socket
import time
from celery.exceptions import SoftTimeLimitExceeded
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.models.task import MatrixTask, TaskStatus
from app.services.queue_estimator import (
    is_task_cancelled,
    update_worker_speed_coeff,
)
from app.worker.celery_app import celery_app
from app.worker.matrix_math import (
    SingularMatrixError,
    TaskCancelledError,
    extract_matrix_preview,
    generate_invertible_matrix,
    invert_matrix_gauss_jordan,
)


def execute_matrix_task_sync(
    task_id: int,
    db_engine=None,
    worker_name: str | None = None,
) -> dict:
    active_engine = db_engine or engine
    hostname = worker_name or socket.gethostname()
    start_ts = time.perf_counter()

    with Session(active_engine) as session:
        task = session.get(MatrixTask, task_id)
        if not task:
            return {"status": "not_found", "task_id": task_id}

        if task.status == TaskStatus.CANCELLED or is_task_cancelled(task_id, session):
            task.status = TaskStatus.CANCELLED
            task.current_stage = "Задачу скасовано до початку обчислень"
            task.completed_at = datetime.now(timezone.utc)
            session.add(task)
            session.commit()
            return {"status": TaskStatus.CANCELLED.value, "task_id": task_id}

        task.status = TaskStatus.PROCESSING
        task.worker_hostname = hostname
        task.started_at = datetime.now(timezone.utc)
        task.progress = 2
        task.current_stage = "Підготовка вхідної матриці"
        session.add(task)
        session.commit()

        matrix_size = task.matrix_size
        is_random = task.is_random
        raw_input_json = task.input_matrix_json

    try:
        if is_random or not raw_input_json:
            input_matrix = generate_invertible_matrix(matrix_size)
            with Session(active_engine) as session:
                task = session.get(MatrixTask, task_id)
                if task and matrix_size <= 30:
                    task.input_matrix_json = json.dumps(input_matrix)
                    session.add(task)
                    session.commit()
        else:
            input_matrix = json.loads(raw_input_json)

        def on_progress(pct: int, stage_text: str) -> None:
            with Session(active_engine) as session:
                t = session.get(MatrixTask, task_id)
                if t and t.status == TaskStatus.PROCESSING:
                    t.progress = pct
                    t.current_stage = stage_text
                    session.add(t)
                    session.commit()

        def check_cancelled() -> bool:
            with Session(active_engine) as session:
                return is_task_cancelled(task_id, session)

        inverse_matrix, residual = invert_matrix_gauss_jordan(
            input_matrix,
            progress_callback=on_progress,
            cancel_check=check_cancelled,
        )

        elapsed = round(time.perf_counter() - start_ts, 4)
        preview = extract_matrix_preview(inverse_matrix, max_dim=5)
        full_json = (
            json.dumps([[round(x, 6) for x in row] for row in inverse_matrix])
            if matrix_size <= 80
            else json.dumps(preview)
        )

        update_worker_speed_coeff(matrix_size, elapsed)

        with Session(active_engine) as session:
            task = session.get(MatrixTask, task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.current_stage = "Обчислення успішно завершено"
                task.result_preview_json = json.dumps(preview)
                task.result_full_json = full_json
                task.residual_norm = residual
                task.execution_time_sec = elapsed
                task.worker_hostname = hostname
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()

        return {
            "status": TaskStatus.COMPLETED.value,
            "task_id": task_id,
            "execution_time_sec": elapsed,
            "residual_norm": residual,
            "worker_hostname": hostname,
        }

    except TaskCancelledError as exc:
        elapsed = round(time.perf_counter() - start_ts, 4)
        with Session(active_engine) as session:
            task = session.get(MatrixTask, task_id)
            if task:
                task.status = TaskStatus.CANCELLED
                task.current_stage = str(exc)
                task.execution_time_sec = elapsed
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
        return {"status": TaskStatus.CANCELLED.value, "task_id": task_id}

    except SoftTimeLimitExceeded:
        elapsed = round(time.perf_counter() - start_ts, 4)
        with Session(active_engine) as session:
            task = session.get(MatrixTask, task_id)
            if task:
                task.status = TaskStatus.TIMEOUT
                task.current_stage = "Перевищено ліміт часу виконання задачі"
                task.error_message = (
                    f"Задача перевищила ліміт часу ({settings.TASK_SOFT_TIME_LIMIT_SEC} сек)"
                )
                task.execution_time_sec = elapsed
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
        return {"status": TaskStatus.TIMEOUT.value, "task_id": task_id}

    except (SingularMatrixError, ValueError) as exc:
        elapsed = round(time.perf_counter() - start_ts, 4)
        with Session(active_engine) as session:
            task = session.get(MatrixTask, task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.current_stage = "Помилка обчислення матриці"
                task.error_message = str(exc)
                task.execution_time_sec = elapsed
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
        return {"status": TaskStatus.FAILED.value, "task_id": task_id, "error": str(exc)}

    except Exception as exc:
        elapsed = round(time.perf_counter() - start_ts, 4)
        with Session(active_engine) as session:
            task = session.get(MatrixTask, task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.current_stage = "Внутрішня помилка воркера"
                task.error_message = str(exc)
                task.execution_time_sec = elapsed
                task.completed_at = datetime.now(timezone.utc)
                session.add(task)
                session.commit()
        return {"status": TaskStatus.FAILED.value, "task_id": task_id, "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.worker.tasks.solve_matrix_inversion_task",
    soft_time_limit=settings.TASK_SOFT_TIME_LIMIT_SEC,
    time_limit=settings.TASK_HARD_TIME_LIMIT_SEC,
)
def solve_matrix_inversion_task(self, task_id: int) -> dict:
    worker_name = self.request.hostname or socket.gethostname()
    return execute_matrix_task_sync(task_id=task_id, worker_name=worker_name)
