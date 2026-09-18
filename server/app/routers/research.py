"""企业背调接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_user
from ..models import (
    CreateResearchRequest,
    ResearchDetail,
    ResearchPage,
    ResearchRecord,
    User,
)
from ..mock.catalog import RESEARCH_QUESTIONS
from ..repositories import research

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/questions", response_model=list[str])
def read_questions() -> list[str]:
    return list(RESEARCH_QUESTIONS)


@router.get("/records", response_model=ResearchPage)
def read_records(user: User = Depends(current_user)) -> ResearchPage:
    return research.summary()


@router.post("/records", response_model=ResearchRecord, status_code=status.HTTP_201_CREATED)
def create_record(payload: CreateResearchRequest, user: User = Depends(current_user)) -> ResearchRecord:
    return research.create(payload.query)


@router.get("/records/{record_id}", response_model=ResearchDetail)
def read_record(record_id: str, user: User = Depends(current_user)) -> ResearchDetail:
    detail = research.detail(record_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调研记录不存在")
    return detail


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_record(record_id: str, user: User = Depends(current_user)) -> None:
    if not research.delete(record_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调研记录不存在")
