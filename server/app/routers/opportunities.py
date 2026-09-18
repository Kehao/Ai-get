"""商机洞察接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import current_user
from ..models import OpportunityPage, User
from ..repositories.opportunities import RANGE_PROFILES, build_page

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

_DEFAULT_RANGE = RANGE_PROFILES[0].key


@router.get("", response_model=OpportunityPage)
def read_opportunities(
    range_key: str = Query(default=_DEFAULT_RANGE, alias="range"),
    user: User = Depends(current_user),
) -> OpportunityPage:
    return build_page(range_key)
