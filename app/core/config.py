import socket
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Matrix Inversion Distributed Service"
    API_V1_STR: str = "/api"
    INSTANCE_HOSTNAME: str = socket.gethostname()

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "matrix_db"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/matrix_db"

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    SECRET_KEY: str = "super-secret-jwt-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    FIRST_ADMIN_USERNAME: str = "admin"
    FIRST_ADMIN_EMAIL: str = "admin@example.com"
    FIRST_ADMIN_PASSWORD: str = "admin123"

    MAX_MATRIX_SIZE: int = 600
    MIN_MATRIX_SIZE: int = 2
    MAX_ACTIVE_TASKS_PER_USER: int = 2
    MAX_HISTORY_TASKS_PER_USER: int = 20
    TASK_SOFT_TIME_LIMIT_SEC: int = 60
    TASK_HARD_TIME_LIMIT_SEC: int = 70

    MIN_WORKERS: int = 2
    MAX_WORKERS: int = 4

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
