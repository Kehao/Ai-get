"""智能体接口：系统模板只读，用户自建智能体可增删改与发布。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_user
from ..models import (
    Agent,
    AgentTemplate,
    CreateAgentRequest,
    UpdateAgentRequest,
    User,
)
from ..repositories import agents

router = APIRouter(prefix="/api/agents", tags=["agents"])

_PUBLISHED_LABEL = "已发布"


@router.get("/templates", response_model=list[AgentTemplate])
def read_templates() -> list[AgentTemplate]:
    return agents.templates()


@router.get("", response_model=list[Agent])
def read_agents(user: User = Depends(current_user)) -> list[Agent]:
    return agents.all()


@router.post("", response_model=Agent, status_code=status.HTTP_201_CREATED)
def create_agent(payload: CreateAgentRequest, user: User = Depends(current_user)) -> Agent:
    return agents.create(payload)


@router.get("/{agent_id}", response_model=Agent)
def read_agent(agent_id: str, user: User = Depends(current_user)) -> Agent:
    return _require_agent(agent_id)


@router.patch("/{agent_id}", response_model=Agent)
def update_agent(agent_id: str, payload: UpdateAgentRequest, user: User = Depends(current_user)) -> Agent:
    agent = agents.update(agent_id, payload)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    return agent


@router.post("/{agent_id}/publish", response_model=Agent)
def publish_agent(agent_id: str, user: User = Depends(current_user)) -> Agent:
    _require_agent(agent_id)
    agent = agents.update(agent_id, UpdateAgentRequest(status_label=_PUBLISHED_LABEL))
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_agent(agent_id: str, user: User = Depends(current_user)) -> None:
    if not agents.delete(agent_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")


def _require_agent(agent_id: str) -> Agent:
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    return agent
