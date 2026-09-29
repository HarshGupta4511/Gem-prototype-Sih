"""Shared FastAPI dependencies: DB session, current user, role gating."""
from collections.abc import Generator
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.database.session import SessionLocal
from app.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    """Return the authenticated User, or 401 when the token is bad/unknown."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except ValueError:
        raise credentials_exc from None
    subject = payload.get("sub")
    try:
        user_id = int(subject) if subject is not None else None
    except (TypeError, ValueError):
        user_id = None
    if user_id is None:
        raise credentials_exc
    user = db.get(User, user_id)
    if user is None:
        raise credentials_exc
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    """Dependency factory: 403 unless the current user's role is allowed."""
    def _role_dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return user

    return _role_dependency
