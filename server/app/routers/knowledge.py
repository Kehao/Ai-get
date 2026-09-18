"""知识库接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_user
from ..models import (
    CreateKnowledgeBaseRequest,
    KnowledgeBase,
    KnowledgeBaseDetail,
    User,
)
from ..repositories import knowledge

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeBase])
def read_knowledge_bases(user: User = Depends(current_user)) -> list[KnowledgeBase]:
    return knowledge.all()


@router.post("", response_model=KnowledgeBaseDetail, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    user: User = Depends(current_user),
) -> KnowledgeBaseDetail:
    return knowledge.create(payload)


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseDetail)
def read_knowledge_base(knowledge_base_id: str, user: User = Depends(current_user)) -> KnowledgeBaseDetail:
    detail = knowledge.detail(knowledge_base_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return detail


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_knowledge_base(knowledge_base_id: str, user: User = Depends(current_user)) -> None:
    if not knowledge.delete(knowledge_base_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
