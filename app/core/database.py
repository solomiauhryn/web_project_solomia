from collections.abc import Generator
from sqlmodel import Session, SQLModel, create_engine, select
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User, UserRole

connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
)


def seed_default_admin(session: Session) -> None:
    admin = session.exec(
        select(User).where(User.username == settings.FIRST_ADMIN_USERNAME)
    ).first()
    if not admin:
        admin_user = User(
            username=settings.FIRST_ADMIN_USERNAME,
            email=settings.FIRST_ADMIN_EMAIL,
            hashed_password=get_password_hash(settings.FIRST_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        session.commit()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_default_admin(session)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
