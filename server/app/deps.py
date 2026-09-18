"""共享依赖：从 Authorization 头解析当前登录用户。"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from .models import User
from .repositories import users
from .security import read_token

_BEARER_PREFIX = "bearer "


def current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少访问令牌")

    token = authorization[len(_BEARER_PREFIX) :].strip()
    email = read_token(token)
    if email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="访问令牌无效或已过期")

    user = users.find(email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user
