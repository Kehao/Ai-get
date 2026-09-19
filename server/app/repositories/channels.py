"""渠道连接仓库。

渠道状态只有三种：可连接、已连接、即将支持。渠道之间不做任何能力门槛判断，
能否连接完全取决于状态本身。
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
        self._lock = threading.RLock()

    def page(self) -> ConnectPage:
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
