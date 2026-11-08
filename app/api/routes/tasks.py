from datetime import datetime, timezone
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.models.task import MatrixTask, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import (
    TaskCreateRequest,
    TaskHistoryResponse,
    TaskResultResponse,
    TaskStatusResponse,
)
from app.services.queue_estimator import (
    get_queue_position_and_eta,
    set_task_cancel_flag,
)
from app.worker.celery_app import celery_app
from app.worker.tasks import execute_matrix_task_sync, solve_matrix_inversion_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


def build_task_status_response(
    session: Session,
    task: MatrixTask,
) -> TaskStatusResponse:
    queue_pos, eta_sec = get_queue_position_and_eta(session, task)
    queue_msg: Optional[str] = None
    if task.status == TaskStatus.QUEUED:
        queue_msg = (
            f"Запит поставлено у чергу (позиція №{queue_pos}). "
            f"Орієнтовний час очікування: ~{eta_sec} сек."
        )
    elif task.status == TaskStatus.PROCESSING:
        queue_msg = (
            f"Задача виконується на сервері {task.worker_hostname or 'worker'}. "
            f"Залишилось приблизно ~{eta_sec} сек."
        )

    preview = None
    if task.result_preview_json:
        try:
            preview = json.loads(task.result_preview_json)
        except Exception:
            preview = None

    return TaskStatusResponse(
        id=task.id,
        user_id=task.user_id,
        celery_task_id=task.celery_task_id,
        matrix_size=task.matrix_size,
        is_random=task.is_random,
        status=task.status,
        progress=task.progress,
        current_stage=task.current_stage,
        queue_position=queue_pos,
        estimated_wait_sec=eta_sec,
        queue_message=queue_msg,
        residual_norm=task.residual_norm,
        result_preview=preview,
        error_message=task.error_message,
        worker_hostname=task.worker_hostname,
        served_by_instance=settings.INSTANCE_HOSTNAME,
        execution_time_sec=task.execution_time_sec,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def enforce_history_quota(session: Session, user_id: int) -> None:
    finished_statuses = [
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.TIMEOUT,
    ]
    user_tasks = session.exec(
        select(MatrixTask)
        .where(MatrixTask.user_id == user_id)
        .order_by(MatrixTask.created_at.desc(), MatrixTask.id.desc())
    ).all()

    if len(user_tasks) >= settings.MAX_HISTORY_TASKS_PER_USER:
        removable = [t for t in reversed(user_tasks) if t.status in finished_statuses]
        excess = len(user_tasks) - settings.MAX_HISTORY_TASKS_PER_USER + 1
        for old_task in removable[:excess]:
            session.delete(old_task)
        session.commit()


@router.post("", response_model=TaskStatusResponse, status_code=status.HTTP_201_CREATED)
def create_matrix_task(
    payload: TaskCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    active_tasks = session.exec(
        select(MatrixTask).where(
            MatrixTask.user_id == current_user.id,
            MatrixTask.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING]),
        )
    ).all()

    if len(active_tasks) >= settings.MAX_ACTIVE_TASKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Перевищено ліміт одночасно активних задач ({settings.MAX_ACTIVE_TASKS_PER_USER}). "
                "Дочекайтесь завершення або скасуйте поточну задачу."
            ),
        )

    enforce_history_quota(session, current_user.id)

    input_json = (
        json.dumps(payload.input_matrix)
        if (not payload.generate_random and payload.input_matrix)
        else None
    )

    task = MatrixTask(
        user_id=current_user.id,
        matrix_size=payload.matrix_size,
        is_random=payload.generate_random,
        status=TaskStatus.QUEUED,
        progress=0,
        current_stage="Запит поставлено у чергу воркерів",
        input_matrix_json=input_json,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    if payload.execute_immediately:
        execute_matrix_task_sync(task.id, db_engine=session.get_bind())
        session.refresh(task)
    else:
        try:
            async_res = solve_matrix_inversion_task.delay(task.id)
            task.celery_task_id = async_res.id
            session.add(task)
            session.commit()
            session.refresh(task)
        except Exception:
            pass

    return build_task_status_response(session, task)


@router.get("", response_model=TaskHistoryResponse)
def list_user_tasks(
    status_filter: Optional[TaskStatus] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskHistoryResponse:
    stmt = select(MatrixTask).where(MatrixTask.user_id == current_user.id)
    if status_filter:
        stmt = stmt.where(MatrixTask.status == status_filter)
    stmt = stmt.order_by(MatrixTask.created_at.desc(), MatrixTask.id.desc()).limit(limit)

    tasks = session.exec(stmt).all()
    active_count = len(
        session.exec(
            select(MatrixTask).where(
                MatrixTask.user_id == current_user.id,
                MatrixTask.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING]),
            )
        ).all()
    )

    items = [build_task_status_response(session, t) for t in tasks]
    return TaskHistoryResponse(
        items=items,
        total=len(items),
        active_count=active_count,
        max_active_limit=settings.MAX_ACTIVE_TASKS_PER_USER,
        max_history_limit=settings.MAX_HISTORY_TASKS_PER_USER,
        served_by_instance=settings.INSTANCE_HOSTNAME,
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_task_status(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    task = session.get(MatrixTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задачу не знайдено",
        )
    if task.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Немає доступу до цієї задачі",
        )
    return build_task_status_response(session, task)


@router.get("/{task_id}/result", response_model=TaskResultResponse)
def get_task_result(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskResultResponse:
    task = session.get(MatrixTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задачу не знайдено",
        )
    if task.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Немає доступу до цієї задачі",
        )
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Результат ще не готовий (поточний статус: {task.status.value})",
        )

    input_mat = json.loads(task.input_matrix_json) if task.input_matrix_json else None
    inv_mat = json.loads(task.result_full_json) if task.result_full_json else None

    return TaskResultResponse(
        task_id=task.id,
        matrix_size=task.matrix_size,
        status=task.status,
        residual_norm=task.residual_norm,
        execution_time_sec=task.execution_time_sec,
        worker_hostname=task.worker_hostname,
        input_matrix=input_mat,
        inverse_matrix=inv_mat,
    )


@router.post("/{task_id}/cancel", response_model=TaskStatusResponse)
def cancel_task(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    task = session.get(MatrixTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задачу не знайдено",
        )
    if task.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Немає доступу до цієї задачі",
        )

    if task.status not in (TaskStatus.QUEUED, TaskStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неможливо скасувати задачу у статусі {task.status.value}",
        )

    set_task_cancel_flag(task.id)
    if task.celery_task_id:
        try:
            celery_app.control.revoke(task.celery_task_id, terminate=True)
        except Exception:
            pass

    task.status = TaskStatus.CANCELLED
    task.current_stage = "Задачу скасовано користувачем"
    task.completed_at = datetime.now(timezone.utc)
    session.add(task)
    session.commit()
    session.refresh(task)

    return build_task_status_response(session, task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_from_history(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    task = session.get(MatrixTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задачу не знайдено",
        )
    if task.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Немає доступу до цієї задачі",
        )
    if task.status in (TaskStatus.QUEUED, TaskStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Спочатку скасуйте активну задачу перед видаленням",
        )

    session.delete(task)
    session.commit()
