from fastapi import APIRouter, Depends, status

from app.core.security import get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.auth import authenticate_admin, create_access_token_for_user

router = APIRouter()


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest) -> TokenResponse:
    user = authenticate_admin(payload)
    access_token = create_access_token_for_user(user)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    return current_user

