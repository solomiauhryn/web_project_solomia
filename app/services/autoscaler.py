from datetime import datetime, timezone
import json
from typing import Any, Optional
from sqlmodel import Session, select

from app.core.config import settings
from app.models.task import MatrixTask, TaskStatus
from app.services.queue_estimator import ACTIVE_WORKERS_KEY, get_redis_client

AUTOSCALER_STATE_KEY = "matrix:autoscaler:state"


def _default_state() -> dict[str, Any]:
    return {
        "current_workers": settings.MIN_WORKERS,
        "min_workers": settings.MIN_WORKERS,
        "max_workers": settings.MAX_WORKERS,
        "auto_scale_enabled": True,
        "last_action": "Ініціалізовано базовий пул воркерів",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_autoscaler_state() -> dict[str, Any]:
    client = get_redis_client()
    if client:
        try:
            raw = client.get(AUTOSCALER_STATE_KEY)
            if raw:
                data = json.loads(raw)
                data["min_workers"] = settings.MIN_WORKERS
                data["max_workers"] = settings.MAX_WORKERS
                return data
        except Exception:
            pass
    return _default_state()


def save_autoscaler_state(state: dict[str, Any]) -> dict[str, Any]:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    client = get_redis_client()
    if client:
        try:
            client.set(AUTOSCALER_STATE_KEY, json.dumps(state))
            client.set(ACTIVE_WORKERS_KEY, str(state["current_workers"]))
        except Exception:
            pass
    return state


def _manage_docker_worker_containers(target_workers: int) -> Optional[str]:
    try:
        import docker

        dclient = docker.from_env()
        for idx in range(3, settings.MAX_WORKERS + 1):
            cname = f"celery_worker_{idx}"
            if idx <= target_workers:
                try:
                    cont = dclient.containers.get(cname)
                    if cont.status != "running":
                        cont.start()
                except Exception:
                    pass
            else:
                try:
                    cont = dclient.containers.get(cname)
                    if cont.status == "running":
                        cont.stop(timeout=5)
                except Exception:
                    pass
        return "docker_synced"
    except Exception:
        return None


def scale_workers_to(
    target_workers: int,
    auto_scale_enabled: Optional[bool] = None,
    reason: str = "Ручне масштабування адміністратором",
) -> dict[str, Any]:
    if target_workers < 1 or target_workers > settings.MAX_WORKERS:
        raise ValueError(
            f"Кількість серверів-воркерів має бути в межах від 1 до {settings.MAX_WORKERS}"
        )

    state = get_autoscaler_state()
    prev = state["current_workers"]
    state["current_workers"] = target_workers
    if auto_scale_enabled is not None:
        state["auto_scale_enabled"] = auto_scale_enabled
    state["last_action"] = f"{reason}: {prev} -> {target_workers} інстансів"
    _manage_docker_worker_containers(target_workers)
    return save_autoscaler_state(state)


def evaluate_autoscale(session: Session) -> dict[str, Any]:
    state = get_autoscaler_state()
    if not state.get("auto_scale_enabled", True):
        return state

    queued_count = len(
        session.exec(
            select(MatrixTask).where(MatrixTask.status == TaskStatus.QUEUED)
        ).all()
    )
    processing_count = len(
        session.exec(
            select(MatrixTask).where(MatrixTask.status == TaskStatus.PROCESSING)
        ).all()
    )

    current = int(state.get("current_workers", settings.MIN_WORKERS))
    target = current
    reason = state.get("last_action", "Стабільний стан")

    if queued_count >= 2 and current < settings.MAX_WORKERS:
        needed = min(
            settings.MAX_WORKERS,
            current + max(1, queued_count // 2),
        )
        if needed > current:
            target = needed
            reason = (
                f"Автоматичне горизонтальне розширення (у черзі {queued_count} задач)"
            )
    elif (
        queued_count == 0
        and processing_count < current
        and current > settings.MIN_WORKERS
    ):
        target = max(settings.MIN_WORKERS, max(processing_count, current - 1))
        if target < current:
            reason = "Автоматичне зменшення пулу воркерів після спаду навантаження"

    if target != current:
        state["current_workers"] = target
        state["last_action"] = f"{reason}: {current} -> {target}"
        _manage_docker_worker_containers(target)
        save_autoscaler_state(state)

    return state
