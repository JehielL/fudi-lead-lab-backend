import secrets

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, UserResponse


def authenticate_admin(payload: LoginRequest) -> UserResponse:
    settings = get_settings()
    expected_password = settings.admin_password.get_secret_value()
    username_ok = secrets.compare_digest(payload.username, settings.admin_username)
    password_ok = secrets.compare_digest(payload.password, expected_password)
    if not username_ok or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserResponse(
        username=settings.admin_username,
        display_name=settings.admin_display_name,
        roles=["admin"],
    )


def create_access_token_for_user(user: UserResponse) -> str:
    return create_access_token(
        subject=user.username,
        claims={"roles": user.roles, "display_name": user.display_name},
    )

