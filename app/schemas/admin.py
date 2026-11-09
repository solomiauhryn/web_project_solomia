from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.task import TaskStatus


class WorkerNodeStatus(BaseModel):
    name: str
    status: str
    active_task_id: Optional[int] = None
    active_matrix_size: Optional[int] = None
    active_progress: Optional[int] = None


class BackendNodeStatus(BaseModel):
    hostname: str
    status: str
    is_current_responder: bool


class AutoscalerStatus(BaseModel):
    current_workers: int
    min_workers: int
    max_workers: int
    auto_scale_enabled: bool
    last_action: str
    updated_at: str


class SystemMetrics(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float


class AdminOverviewResponse(BaseModel):
    served_by_instance: str
    system_metrics: SystemMetrics
    autoscaler: AutoscalerStatus
    backend_nodes: list[BackendNodeStatus]
    worker_nodes: list[WorkerNodeStatus]
    queued_tasks: int
    processing_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    timeout_tasks: int
    total_users: int


class ScaleWorkersRequest(BaseModel):
    target_workers: int = Field(ge=1, le=10)
    auto_scale_enabled: Optional[bool] = None


class AdminTaskItem(BaseModel):
    id: int
    user_id: int
    username: str
    matrix_size: int
    status: TaskStatus
    progress: int
    current_stage: str
    worker_hostname: Optional[str] = None
    execution_time_sec: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
