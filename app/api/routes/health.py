from datetime import datetime, timezone
import os
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlmodel import Session
import redis

from app.core.config import settings
from app.core.database import get_session

router = APIRouter(tags=["health"])

BACKEND_HEARTBEAT_PREFIX = "matrix:backend:node:"


def register_backend_heartbeat() -> None:
    try:
        r = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=0.5,
            decode_responses=True,
        )
        r.setex(
            f"{BACKEND_HEARTBEAT_PREFIX}{settings.INSTANCE_HOSTNAME}",
            30,
            datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        pass


@router.get("/health")
def health_check(session: Session = Depends(get_session)) -> dict:
    register_backend_heartbeat()
    db_status = "healthy"
    try:
        session.exec(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    redis_status = "healthy"
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
    except Exception as exc:
        redis_status = f"unavailable: {exc}"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "service": settings.PROJECT_NAME,
        "instance_hostname": settings.INSTANCE_HOSTNAME,
        "database": db_status,
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/cluster/node")
def get_cluster_node_info(request: Request) -> dict:
    register_backend_heartbeat()
    return {
        "instance_hostname": settings.INSTANCE_HOSTNAME,
        "pid": os.getpid(),
        "forwarded_for": request.headers.get("X-Forwarded-For", "direct"),
        "forwarded_proto": request.headers.get("X-Forwarded-Proto", "http"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
