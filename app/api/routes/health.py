from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session
import redis

from app.core.config import settings
from app.core.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(session: Session = Depends(get_session)) -> dict:
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
