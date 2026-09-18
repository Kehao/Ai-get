"""仓库单例。

进程内共享同一份内存状态，路由层通过这里的实例读写数据。
"""

from __future__ import annotations

from .agents import AgentRepository
from .channels import ChannelRepository
from .knowledge import KnowledgeRepository
from .research import ResearchRepository
from .settings import SettingsRepository
from .targets import TargetListRepository
from .users import UserRepository

users = UserRepository()
target_lists = TargetListRepository()
research = ResearchRepository()
agents = AgentRepository()
channels = ChannelRepository()
knowledge = KnowledgeRepository()
settings = SettingsRepository()

__all__ = [
    "agents",
    "channels",
    "knowledge",
    "research",
    "settings",
    "target_lists",
    "users",
]
