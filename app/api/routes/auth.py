from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import Token, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def build_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        max_matrix_size=settings.MAX_MATRIX_SIZE,
        max_active_tasks=settings.MAX_ACTIVE_TASKS_PER_USER,
        max_history_tasks=settings.MAX_HISTORY_TASKS_PER_USER,
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
) -> Token:
    existing_user = session.exec(
        select(User).where(
            (User.username == payload.username) | (User.email == payload.email)
        )
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Користувач з таким ім'ям або email вже існує",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role=UserRole.USER,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    access_token = create_access_token(subject=user.id, role=user.role.value)
    return Token(
        access_token=access_token,
        user=build_user_read(user),
    )


@router.post("/login", response_model=Token)
def login_user(
    payload: UserLogin,
    session: Session = Depends(get_session),
) -> Token:
    user = session.exec(
        select(User).where(User.username == payload.username)
    ).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невірний логін або пароль",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Обліковий запис деактивовано",
        )

    access_token = create_access_token(subject=user.id, role=user.role.value)
    return Token(
        access_token=access_token,
        user=build_user_read(user),
    )


@router.post("/login/token", response_model=Token)
def login_oauth2_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> Token:
    return login_user(
        UserLogin(username=form_data.username, password=form_data.password),
        session=session,
    )


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return build_user_read(current_user)
