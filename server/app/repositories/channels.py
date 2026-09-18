"""渠道连接仓库。

套餐相关的解锁判断在这里完成：免费版可直接连接邮箱渠道，
社媒渠道返回明确的升级提示，而不是静默失败。
"""

from __future__ import annotations

import threading

from ..models import Channel, ChannelGroup, ConnectPage, ConnectSummary
from ..mock.catalog import COMING_SOON_CHANNELS, EMAIL_CHANNEL, SOCIAL_CHANNELS

_GROUP_ORDER = ("邮箱渠道", "社媒渠道", "即将支持")


class ChannelRepository:
    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {
            channel.id: channel.model_copy()
            for channel in (EMAIL_CHANNEL, *SOCIAL_CHANNELS, *COMING_SOON_CHANNELS)
        }
        self._channels[EMAIL_CHANNEL.id].state = "available"
        self._lock = threading.RLock()

    def page(self, plan_name: str) -> ConnectPage:
        with self._lock:
            grouped = [
                ChannelGroup(
                    group=group,
                    channels=[channel for channel in self._channels.values() if channel.group == group],
                )
                for group in _GROUP_ORDER
            ]
            email_channels = [item for item in self._channels.values() if item.group == "邮箱渠道"]
            social_channels = [item for item in self._channels.values() if item.group == "社媒渠道"]
            return ConnectPage(
                summary=ConnectSummary(
                    plan_name=plan_name,
                    connected_email=sum(1 for item in email_channels if item.state == "connected"),
                    total_email=len(email_channels),
                    connected_social=sum(1 for item in social_channels if item.state == "connected"),
                    total_social=len(social_channels),
                ),
                groups=grouped,
            )

    def connect(self, channel_id: str, account_label: str) -> Channel:
        with self._lock:
            channel = self._require(channel_id)
            if channel.state == "coming_soon":
                raise ValueError(f"{channel.name} 渠道即将支持，暂时无法连接")
            if channel.state == "locked":
                raise ValueError(f"{channel.name} 需要升级到 {channel.required_plan} 套餐后才能连接")
            channel.state = "connected"
            channel.account_label = account_label
            return channel

    def disconnect(self, channel_id: str) -> Channel:
        with self._lock:
            channel = self._require(channel_id)
            if channel.state != "connected":
                raise ValueError(f"{channel.name} 当前未连接")
            channel.state = "available"
            channel.account_label = None
            return channel

    def _require(self, channel_id: str) -> Channel:
        channel = self._channels.get(channel_id)
        if channel is None:
            raise ValueError(f"渠道不存在：{channel_id}")
        return channel
