from datetime import datetime
from pydantic import BaseModel, Field
from app.models.user import UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(
        min_length=5,
        max_length=128,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    max_matrix_size: int
    max_active_tasks: int
    max_history_tasks: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
