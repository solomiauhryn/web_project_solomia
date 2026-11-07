from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "matrix_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("matrix_size", sa.Integer(), nullable=False),
        sa.Column("is_random", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(length=255), nullable=False),
        sa.Column("input_matrix_json", sa.Text(), nullable=True),
        sa.Column("result_preview_json", sa.Text(), nullable=True),
        sa.Column("result_full_json", sa.Text(), nullable=True),
        sa.Column("residual_norm", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("worker_hostname", sa.String(length=128), nullable=True),
        sa.Column("execution_time_sec", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_matrix_tasks_celery_task_id"),
        "matrix_tasks",
        ["celery_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matrix_tasks_created_at"),
        "matrix_tasks",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matrix_tasks_status"),
        "matrix_tasks",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matrix_tasks_user_id"),
        "matrix_tasks",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_matrix_tasks_user_id"), table_name="matrix_tasks")
    op.drop_index(op.f("ix_matrix_tasks_status"), table_name="matrix_tasks")
    op.drop_index(op.f("ix_matrix_tasks_created_at"), table_name="matrix_tasks")
    op.drop_index(op.f("ix_matrix_tasks_celery_task_id"), table_name="matrix_tasks")
    op.drop_table("matrix_tasks")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
