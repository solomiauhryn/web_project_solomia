from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
import psutil
from sqlmodel import Session, select

from app.api.deps import get_current_admin
from app.api.routes.health import BACKEND_HEARTBEAT_PREFIX, register_backend_heartbeat
from app.core.config import settings
from app.core.database import get_session
from app.models.task import MatrixTask, TaskStatus
from app.models.user import User
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminTaskItem,
    AutoscalerStatus,
    BackendNodeStatus,
    ScaleWorkersRequest,
    SystemMetrics,
    WorkerNodeStatus,
)
from app.services.autoscaler import evaluate_autoscale, scale_workers_to
from app.services.queue_estimator import get_redis_client, set_task_cancel_flag
from app.worker.celery_app import celery_app

router = APIRouter(prefix="/admin", tags=["admin"])


def _collect_backend_nodes() -> list[BackendNodeStatus]:
    register_backend_heartbeat()
    discovered: set[str] = {"backend-1", "backend-2", settings.INSTANCE_HOSTNAME}
    client = get_redis_client()
    if client:
        try:
            for key in client.keys(f"{BACKEND_HEARTBEAT_PREFIX}*"):
                node_name = key.replace(BACKEND_HEARTBEAT_PREFIX, "")
                if node_name:
                    discovered.add(node_name)
        except Exception:
            pass

    nodes: list[BackendNodeStatus] = []
    for name in sorted(discovered):
        nodes.append(
            BackendNodeStatus(
                hostname=name,
                status="ONLINE",
                is_current_responder=(name == settings.INSTANCE_HOSTNAME),
            )
        )
    return nodes


def _collect_worker_nodes(
    current_workers: int,
    processing_tasks: list[MatrixTask],
) -> list[WorkerNodeStatus]:
    nodes: list[WorkerNodeStatus] = []
    for idx in range(1, current_workers + 1):
        wname = f"celery_worker_{idx}"
        assigned = processing_tasks[idx - 1] if idx - 1 < len(processing_tasks) else None
        if assigned:
            nodes.append(
                WorkerNodeStatus(
                    name=assigned.worker_hostname or wname,
                    status="BUSY",
                    active_task_id=assigned.id,
                    active_matrix_size=assigned.matrix_size,
                    active_progress=assigned.progress,
                )
            )
        else:
            nodes.append(
                WorkerNodeStatus(
                    name=wname,
                    status="IDLE",
                )
            )
    return nodes


@router.get("/overview", response_model=AdminOverviewResponse)
def get_admin_overview(
    session: Session = Depends(get_session),
    _admin: User = Depends(get_current_admin),
) -> AdminOverviewResponse:
    autoscale_state = evaluate_autoscale(session)
    all_tasks = session.exec(select(MatrixTask)).all()
    users_count = len(session.exec(select(User)).all())

    processing_list = [t for t in all_tasks if t.status == TaskStatus.PROCESSING]
    queued_count = sum(1 for t in all_tasks if t.status == TaskStatus.QUEUED)
    completed_count = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
    failed_count = sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)
    cancelled_count = sum(1 for t in all_tasks if t.status == TaskStatus.CANCELLED)
    timeout_count = sum(1 for t in all_tasks if t.status == TaskStatus.TIMEOUT)

    vm = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=None)

    current_workers = int(autoscale_state["current_workers"])

    return AdminOverviewResponse(
        served_by_instance=settings.INSTANCE_HOSTNAME,
        system_metrics=SystemMetrics(
            cpu_percent=round(cpu_pct, 1),
            memory_percent=round(vm.percent, 1),
            memory_used_mb=round(vm.used / (1024 * 1024), 1),
            memory_total_mb=round(vm.total / (1024 * 1024), 1),
        ),
        autoscaler=AutoscalerStatus(**autoscale_state),
        backend_nodes=_collect_backend_nodes(),
        worker_nodes=_collect_worker_nodes(current_workers, processing_list),
        queued_tasks=queued_count,
        processing_tasks=len(processing_list),
        completed_tasks=completed_count,
        failed_tasks=failed_count,
        cancelled_tasks=cancelled_count,
        timeout_tasks=timeout_count,
        total_users=users_count,
    )


@router.get("/tasks", response_model=list[AdminTaskItem])
def list_all_tasks_for_admin(
    session: Session = Depends(get_session),
    _admin: User = Depends(get_current_admin),
) -> list[AdminTaskItem]:
    tasks = session.exec(
        select(MatrixTask).order_by(MatrixTask.created_at.desc(), MatrixTask.id.desc()).limit(50)
    ).all()
    users_map = {u.id: u.username for u in session.exec(select(User)).all()}

    return [
        AdminTaskItem(
            id=t.id,
            user_id=t.user_id,
            username=users_map.get(t.user_id, f"user_{t.user_id}"),
            matrix_size=t.matrix_size,
            status=t.status,
            progress=t.progress,
            current_stage=t.current_stage,
            worker_hostname=t.worker_hostname,
            execution_time_sec=t.execution_time_sec,
            created_at=t.created_at,
            completed_at=t.completed_at,
        )
        for t in tasks
    ]


@router.post("/workers/scale", response_model=AutoscalerStatus)
def scale_worker_pool(
    payload: ScaleWorkersRequest,
    _admin: User = Depends(get_current_admin),
) -> AutoscalerStatus:
    if payload.target_workers > settings.MAX_WORKERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Перевищено максимальний ліміт горизонтального масштабування "
                f"(максимум {settings.MAX_WORKERS} серверів)"
            ),
        )
    try:
        state = scale_workers_to(
            target_workers=payload.target_workers,
            auto_scale_enabled=payload.auto_scale_enabled,
        )
        return AutoscalerStatus(**state)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/tasks/{task_id}/cancel")
def admin_force_cancel_task(
    task_id: int,
    session: Session = Depends(get_session),
    _admin: User = Depends(get_current_admin),
) -> dict:
    task = session.get(MatrixTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задачу не знайдено",
        )
    if task.status not in (TaskStatus.QUEUED, TaskStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Задача вже у стані {task.status.value}",
        )

    set_task_cancel_flag(task.id)
    if task.celery_task_id:
        try:
            celery_app.control.revoke(task.celery_task_id, terminate=True)
        except Exception:
            pass

    task.status = TaskStatus.CANCELLED
    task.current_stage = "Задачу примусово зупинено адміністратором"
    task.completed_at = datetime.now(timezone.utc)
    session.add(task)
    session.commit()

    return {"status": "cancelled", "task_id": task.id}
