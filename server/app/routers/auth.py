"""登录与会话相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_user
from ..models import CredentialsRequest, LoginResponse, StatusMessage, User
from ..repositories import users
from ..security import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: CredentialsRequest) -> LoginResponse:
    user = users.authenticate(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    return LoginResponse(token=create_token(user.email), user=user)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: CredentialsRequest) -> LoginResponse:
    user = users.register(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册")
    return LoginResponse(token=create_token(user.email), user=user)


@router.get("/me", response_model=User)
def read_current_user(user: User = Depends(current_user)) -> User:
    return user


@router.post("/logout", response_model=StatusMessage)
def logout() -> StatusMessage:
    """令牌是无状态的，退出登录由前端清除本地令牌完成。"""
    return StatusMessage(message="已退出登录")
