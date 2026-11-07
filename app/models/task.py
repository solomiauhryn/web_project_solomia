from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.user import User


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class MatrixTask(SQLModel, table=True):
    __tablename__ = "matrix_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    celery_task_id: Optional[str] = Field(default=None, index=True, max_length=128)

    matrix_size: int = Field(ge=2, le=1000)
    is_random: bool = Field(default=True)
    status: TaskStatus = Field(default=TaskStatus.QUEUED, index=True)
    progress: int = Field(default=0, ge=0, le=100)
    current_stage: str = Field(default="Очікування у черзі", max_length=255)

    input_matrix_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    result_preview_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    result_full_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    residual_norm: Optional[float] = Field(default=None)

    error_message: Optional[str] = Field(default=None, max_length=1024)
    worker_hostname: Optional[str] = Field(default=None, max_length=128)
    execution_time_sec: Optional[float] = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    user: Optional["User"] = Relationship(back_populates="tasks")
