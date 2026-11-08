from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.models.task import TaskStatus


class TaskCreateRequest(BaseModel):
    matrix_size: int = Field(
        description="Розмірність квадратної матриці N x N",
    )
    generate_random: bool = True
    input_matrix: Optional[list[list[float]]] = None
    execute_immediately: bool = False

    @model_validator(mode="after")
    def validate_complexity_and_matrix(self) -> "TaskCreateRequest":
        if self.matrix_size < settings.MIN_MATRIX_SIZE:
            raise ValueError(
                f"Розмірність матриці не може бути меншою за {settings.MIN_MATRIX_SIZE}"
            )
        if self.matrix_size > settings.MAX_MATRIX_SIZE:
            raise ValueError(
                f"Перевищено максимальну трудомісткість задачі: дозволено максимум N={settings.MAX_MATRIX_SIZE}"
            )

        if not self.generate_random:
            if not self.input_matrix:
                raise ValueError(
                    "Необхідно передати матрицю input_matrix або увімкнути generate_random=true"
                )
            if len(self.input_matrix) != self.matrix_size or any(
                len(row) != self.matrix_size for row in self.input_matrix
            ):
                raise ValueError(
                    f"Вхідна матриця повинна мати точний розмір {self.matrix_size}x{self.matrix_size}"
                )
        return self


class TaskStatusResponse(BaseModel):
    id: int
    user_id: int
    celery_task_id: Optional[str] = None
    matrix_size: int
    is_random: bool
    status: TaskStatus
    progress: int
    current_stage: str
    queue_position: Optional[int] = None
    estimated_wait_sec: Optional[float] = None
    queue_message: Optional[str] = None
    residual_norm: Optional[float] = None
    result_preview: Optional[list[list[float]]] = None
    error_message: Optional[str] = None
    worker_hostname: Optional[str] = None
    served_by_instance: str
    execution_time_sec: Optional[float] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskResultResponse(BaseModel):
    task_id: int
    matrix_size: int
    status: TaskStatus
    residual_norm: Optional[float] = None
    execution_time_sec: Optional[float] = None
    worker_hostname: Optional[str] = None
    input_matrix: Optional[list[list[float]]] = None
    inverse_matrix: Optional[list[list[float]]] = None


class TaskHistoryResponse(BaseModel):
    items: list[TaskStatusResponse]
    total: int
    active_count: int
    max_active_limit: int
    max_history_limit: int
    served_by_instance: str
