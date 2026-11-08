from typing import Optional
from sqlmodel import Session, select
import redis

from app.core.config import settings
from app.models.task import MatrixTask, TaskStatus

DEFAULT_SEC_PER_CUBIC_UNIT = 3.5e-7
CANCEL_KEY_PREFIX = "matrix:cancel:"
SPEED_COEFF_KEY = "matrix:worker:sec_per_n3"
ACTIVE_WORKERS_KEY = "matrix:worker:active_count"


def get_redis_client() -> Optional[redis.Redis]:
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=0.5,
            decode_responses=True,
        )
        client.ping()
        return client
    except Exception:
        return None


def set_task_cancel_flag(task_id: int) -> None:
    client = get_redis_client()
    if client:
        try:
            client.setex(f"{CANCEL_KEY_PREFIX}{task_id}", 3600, "1")
        except Exception:
            pass


def is_task_cancelled(task_id: int, session: Optional[Session] = None) -> bool:
    client = get_redis_client()
    if client:
        try:
            if client.get(f"{CANCEL_KEY_PREFIX}{task_id}") == "1":
                return True
        except Exception:
            pass
    if session:
        task = session.get(MatrixTask, task_id)
        if task and task.status == TaskStatus.CANCELLED:
            return True
    return False


def update_worker_speed_coeff(matrix_size: int, elapsed_sec: float) -> None:
    if matrix_size < 10 or elapsed_sec <= 0:
        return
    coeff = elapsed_sec / float(matrix_size ** 3)
    client = get_redis_client()
    if client:
        try:
            prev = client.get(SPEED_COEFF_KEY)
            if prev:
                blended = 0.7 * float(prev) + 0.3 * coeff
            else:
                blended = coeff
            client.set(SPEED_COEFF_KEY, str(blended))
        except Exception:
            pass


def get_worker_speed_coeff() -> float:
    client = get_redis_client()
    if client:
        try:
            val = client.get(SPEED_COEFF_KEY)
            if val:
                return float(val)
        except Exception:
            pass
    return DEFAULT_SEC_PER_CUBIC_UNIT


def get_active_worker_capacity() -> int:
    client = get_redis_client()
    if client:
        try:
            val = client.get(ACTIVE_WORKERS_KEY)
            if val and int(val) >= 1:
                return int(val)
        except Exception:
            pass
    return max(1, settings.MIN_WORKERS)


def estimate_single_task_seconds(matrix_size: int, progress: int = 0) -> float:
    coeff = get_worker_speed_coeff()
    remaining_ratio = max(0.05, (100 - max(0, min(100, progress))) / 100.0)
    est = coeff * float(matrix_size ** 3) * remaining_ratio
    return round(max(0.5, est), 2)


def get_queue_position_and_eta(
    session: Session,
    target_task: MatrixTask,
) -> tuple[Optional[int], Optional[float]]:
    if target_task.status == TaskStatus.PROCESSING:
        rem = estimate_single_task_seconds(
            target_task.matrix_size,
            target_task.progress,
        )
        return 0, rem

    if target_task.status != TaskStatus.QUEUED:
        return None, None

    processing_tasks = session.exec(
        select(MatrixTask).where(MatrixTask.status == TaskStatus.PROCESSING)
    ).all()

    queued_tasks = session.exec(
        select(MatrixTask)
        .where(MatrixTask.status == TaskStatus.QUEUED)
        .order_by(MatrixTask.created_at.asc(), MatrixTask.id.asc())
    ).all()

    position = 1
    queued_ahead_work = 0.0
    for qt in queued_tasks:
        if qt.id == target_task.id:
            break
        position += 1
        queued_ahead_work += estimate_single_task_seconds(qt.matrix_size, 0)

    processing_work = sum(
        estimate_single_task_seconds(pt.matrix_size, pt.progress)
        for pt in processing_tasks
    )
    own_work = estimate_single_task_seconds(target_task.matrix_size, 0)
    worker_count = max(1, get_active_worker_capacity())

    total_eta = ((processing_work + queued_ahead_work) / worker_count) + own_work
    return position, round(total_eta, 2)
