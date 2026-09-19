"""关联账号（渠道连接）接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import current_user
from ..models import Channel, ConnectPage, User
from ..repositories import channels

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ConnectRequest(BaseModel):
    account_label: str = Field(default="", max_length=120)


@router.get("", response_model=ConnectPage)
def read_channels(user: User = Depends(current_user)) -> ConnectPage:
    return channels.page()


@router.post("/{channel_id}/connect", response_model=Channel)
def connect_channel(
    channel_id: str,
    payload: ConnectRequest,
    user: User = Depends(current_user),
) -> Channel:
    label = payload.account_label.strip() or user.email
    try:
        return channels.connect(channel_id, label)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.delete("/{channel_id}/connect", response_model=Channel)
def disconnect_channel(channel_id: str, user: User = Depends(current_user)) -> Channel:
    try:
        return channels.disconnect(channel_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
