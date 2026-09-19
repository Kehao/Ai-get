"""潜客挖掘接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..deps import current_user
from ..models import (
    AddColumnRequest,
    AddMoreRequest,
    CompanyPage,
    Contact,
    CountOption,
    CreateListRequest,
    CreateOutreachRequest,
    ListDetail,
    OutreachPlan,
    Strategy,
    TargetColumn,
    TargetCompany,
    TargetCompanyDetail,
    TargetList,
    TargetOverview,
    UpdateConditionsRequest,
    UploadResult,
    User,
)
from ..mock.catalog import COUNT_OPTIONS, STRATEGIES
from ..repositories import target_lists

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("/strategies", response_model=list[Strategy])
def read_strategies() -> list[Strategy]:
    return list(STRATEGIES)


@router.get("/count-options", response_model=list[CountOption])
def read_count_options() -> list[CountOption]:
    return list(COUNT_OPTIONS)


@router.get("/lists", response_model=TargetOverview)
def read_overview(user: User = Depends(current_user)) -> TargetOverview:
    company_count, running_count, list_count = target_lists.stats()
    return TargetOverview(
        company_count=company_count,
        running_count=running_count,
        list_count=list_count,
        lists=target_lists.all_lists(),
    )


@router.post("/lists", response_model=TargetList, status_code=status.HTTP_201_CREATED)
def create_list(payload: CreateListRequest, user: User = Depends(current_user)) -> TargetList:
    return target_lists.create_list(payload.query, payload.mode, payload.count)


@router.post("/lists/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_list(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> UploadResult:
    content = await file.read()
    try:
        list_id, imported_rows = target_lists.create_list_from_upload(content)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return UploadResult(list_id=list_id, imported_rows=imported_rows)


@router.get("/lists/{list_id}", response_model=ListDetail)
def read_list_detail(
    list_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    keyword: str = Query(default=""),
    match_level: str = Query(default=""),
    sort: str = Query(default="match"),
    user: User = Depends(current_user),
) -> ListDetail:
    target_list = _require_list(list_id)
    return ListDetail(
        target_list=target_list,
        columns=target_lists.columns(list_id),
        companies=target_lists.page_companies(list_id, page, page_size, keyword, match_level, sort),
    )


@router.get("/lists/{list_id}/companies", response_model=CompanyPage)
def read_companies(
    list_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    keyword: str = Query(default=""),
    match_level: str = Query(default=""),
    sort: str = Query(default="match"),
    user: User = Depends(current_user),
) -> CompanyPage:
    _require_list(list_id)
    return target_lists.page_companies(list_id, page, page_size, keyword, match_level, sort)


@router.post("/lists/{list_id}/columns", response_model=TargetColumn, status_code=status.HTTP_201_CREATED)
def add_column(
    list_id: str,
    payload: AddColumnRequest,
    user: User = Depends(current_user),
) -> TargetColumn:
    _require_list(list_id)
    column = target_lists.add_column(list_id, payload.name)
    if column is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return column


@router.post("/lists/{list_id}/more", response_model=TargetList)
def add_more(
    list_id: str,
    payload: AddMoreRequest,
    user: User = Depends(current_user),
) -> TargetList:
    _require_list(list_id)
    updated = target_lists.add_more(list_id, payload.count)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return updated


@router.patch("/lists/{list_id}/conditions", response_model=TargetList)
def update_conditions(
    list_id: str,
    payload: UpdateConditionsRequest,
    user: User = Depends(current_user),
) -> TargetList:
    _require_list(list_id)
    try:
        updated = target_lists.update_conditions(list_id, payload.query, payload.conditions)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return updated


@router.post("/lists/{list_id}/mine", response_model=TargetList)
def remine(list_id: str, user: User = Depends(current_user)) -> TargetList:
    _require_list(list_id)
    updated = target_lists.remine(list_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return updated


@router.get("/lists/{list_id}/companies/{row_id}", response_model=TargetCompanyDetail)
def read_company_detail(
    list_id: str,
    row_id: str,
    user: User = Depends(current_user),
) -> TargetCompanyDetail:
    _require_list(list_id)
    detail = target_lists.company_detail(list_id, row_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业记录不存在")
    return detail


@router.get("/lists/{list_id}/outreach", response_model=OutreachPlan | None)
def read_outreach(list_id: str, user: User = Depends(current_user)) -> OutreachPlan | None:
    _require_list(list_id)
    return target_lists.outreach(list_id)


@router.post("/lists/{list_id}/outreach", response_model=OutreachPlan, status_code=status.HTTP_201_CREATED)
def create_outreach(
    list_id: str,
    payload: CreateOutreachRequest,
    user: User = Depends(current_user),
) -> OutreachPlan:
    _require_list(list_id)
    plan = target_lists.create_outreach(list_id, payload)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return plan


@router.get("/lists/{list_id}/companies/{row_id}/contacts", response_model=list[Contact])
def read_contacts(list_id: str, row_id: str, user: User = Depends(current_user)) -> list[Contact]:
    _require_list(list_id)
    if target_lists.find_company(list_id, row_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业记录不存在")
    return target_lists.contacts(list_id, row_id)


@router.post("/lists/{list_id}/companies/{row_id}/retry", response_model=TargetCompany)
def retry_field(
    list_id: str,
    row_id: str,
    field: str = Query(alias="field"),
    user: User = Depends(current_user),
) -> TargetCompany:
    _require_list(list_id)
    try:
        company = target_lists.retry_field(list_id, row_id, field)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业记录不存在")
    return company


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_list(list_id: str, user: User = Depends(current_user)) -> None:
    if not target_lists.delete_list(list_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")


def _require_list(list_id: str) -> TargetList:
    target_list = target_lists.get_list(list_id)
    if target_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return target_list
