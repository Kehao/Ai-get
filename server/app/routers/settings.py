"""工作空间设置接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import current_user
from ..models import UpdateSettingsRequest, User, WorkspaceSettings
from ..repositories import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=WorkspaceSettings)
def read_settings(user: User = Depends(current_user)) -> WorkspaceSettings:
    return settings.read()


@router.patch("", response_model=WorkspaceSettings)
def update_settings(payload: UpdateSettingsRequest, user: User = Depends(current_user)) -> WorkspaceSettings:
    return settings.update(payload)
