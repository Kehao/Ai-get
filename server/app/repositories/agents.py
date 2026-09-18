"""智能体仓库：系统模板只读，用户自建智能体可增删改。"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from ..models import Agent, AgentTemplate, CreateAgentRequest, UpdateAgentRequest
from ..mock.catalog import AGENT_TEMPLATES


class AgentRepository:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = threading.RLock()

    def templates(self) -> list[AgentTemplate]:
        return list(AGENT_TEMPLATES)

    def find_template(self, template_id: str) -> AgentTemplate | None:
        return next((item for item in AGENT_TEMPLATES if item.id == template_id), None)

    def all(self) -> list[Agent]:
        with self._lock:
            return sorted(self._agents.values(), key=lambda item: item.created_at, reverse=True)

    def create(self, request: CreateAgentRequest) -> Agent:
        template = self.find_template(request.template_id) if request.template_id else None
        channels = request.channels or (list(template.channels) if template else ["邮件"])
        description = request.description or (template.description if template else "")
        agent = Agent(
            id=f"agent-{uuid.uuid4().hex[:8]}",
            name=request.name,
            emoji=request.emoji,
            description=description,
            status_label="草稿",
            channels=channels,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._agents[agent.id] = agent
        return agent

    def get(self, agent_id: str) -> Agent | None:
        with self._lock:
            return self._agents.get(agent_id)

    def update(self, agent_id: str, request: UpdateAgentRequest) -> Agent | None:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                return None

            if request.name is not None:
                agent.name = request.name
            if request.description is not None:
                agent.description = request.description
            if request.status_label is not None:
                agent.status_label = request.status_label
            return agent

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            return self._agents.pop(agent_id, None) is not None
