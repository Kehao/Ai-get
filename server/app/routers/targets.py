"""潜客挖掘接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..deps import current_user
from ..llm.client import LlmError
from ..models import (
    AddColumnRequest,
    AddMoreRequest,
    AgentDiscoverRequest,
    CompanyPage,
    Contact,
    CountOption,
    CreateListRequest,
    CreateOutreachRequest,
    ListDetail,
    OutreachPlan,
    PersonPage,
    SearchMode,
    SourceInfo,
    Strategy,
    TargetColumn,
    TargetCompany,
    TargetCompanyDetail,
    TargetList,
    TargetOverview,
    TargetPersonDetail,
    UpdateConditionsRequest,
    UploadResult,
    User,
)
from ..mock.catalog import COUNT_OPTIONS, STRATEGIES_BY_MODE
from ..providers import manifests
from ..repositories import target_lists

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("/strategies", response_model=list[Strategy])
def read_strategies(mode: SearchMode = "company") -> list[Strategy]:
    """推荐策略随「找公司 / 找人」切换：两者要圈的实体不同，提示词也就不同。"""
    return list(STRATEGIES_BY_MODE[mode])


@router.get("/sources", response_model=list[SourceInfo])
def read_sources() -> list[SourceInfo]:
    """当前已注册的数据源。

    暴露这个接口有两个用处：让前端说明「这批结果是谁给的」，
    以及让新增爬虫在上线后能立刻被看见——注册即出现在这里，不需要改接口。
    """
    return [
        SourceInfo(
            id=item.id,
            name=item.name,
            description=item.description,
            capabilities=list(item.capabilities),
            regions=list(item.regions),
            priority=item.priority,
            cost_per_call=item.cost_per_call,
            requires_credentials=item.requires_credentials,
        )
        for item in manifests()
    ]


@router.get("/count-options", response_model=list[CountOption])
def read_count_options() -> list[CountOption]:
    return list(COUNT_OPTIONS)


@router.get("/lists", response_model=TargetOverview)
def read_overview(user: User = Depends(current_user)) -> TargetOverview:
    row_count, running_count, list_count = target_lists.stats()
    return TargetOverview(
        row_count=row_count,
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
        # 按模式只填一侧：找人列表没有「行业」「规模」这些列，
        # 用一个字段装两种行会让前端只能按最小公倍数定义列。
        companies=(
            None
            if target_list.mode == "people"
            else target_lists.page_companies(list_id, page, page_size, keyword, match_level, sort)
        ),
        people=(
            target_lists.page_people(list_id, page, page_size, keyword, match_level, sort)
            if target_list.mode == "people"
            else None
        ),
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


@router.get("/lists/{list_id}/people", response_model=PersonPage)
def read_people(
    list_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    keyword: str = Query(default=""),
    match_level: str = Query(default=""),
    sort: str = Query(default="match"),
    user: User = Depends(current_user),
) -> PersonPage:
    """人物列表的一页。

    与 `/companies` 并列而不是让它返回两种形状：接口的响应模型就是前端的类型定义，
    同一个路径按模式返回不同结构会让「列表有两种行」这件事藏在运行时。
    """
    _require_list(list_id)
    return target_lists.page_people(list_id, page, page_size, keyword, match_level, sort)


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


@router.get("/lists/{list_id}/people/{row_id}", response_model=TargetPersonDetail)
def read_person_detail(
    list_id: str,
    row_id: str,
    user: User = Depends(current_user),
) -> TargetPersonDetail:
    """人物详情面板。区块骨架与会社详情一致，内容换成档案与人物侧的调研项。"""
    _require_list(list_id)
    detail = target_lists.person_detail(list_id, row_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人物记录不存在")
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


@router.post("/lists/{list_id}/companies/{row_id}/deep-dive", response_model=TargetCompany)
def deep_dive_company(
    list_id: str,
    row_id: str,
    user: User = Depends(current_user),
) -> TargetCompany:
    """对一行企业执行深挖：抓页面、定位官网，用 LLM 把档案字段补齐。

    做成显式动作为主是因为它**贵而慢**——一次请求十几秒、含 LLM 调用与外部抓取，
    还会产生真实费用，所以不在建列表时自动跑。深挖过程中 LLM 不可用时不算接口失败：
    结果里会带 `dossier_state="failed"` 与原因。
    """
    _require_list(list_id)
    try:
        company = target_lists.deep_dive_company(list_id, row_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业记录不存在")
    return company


@router.post("/agent-discover", response_model=TargetList, status_code=status.HTTP_201_CREATED)
def agent_discover(
    payload: AgentDiscoverRequest,
    user: User = Depends(current_user),
) -> TargetList:
    """创建一次「智能发现」：检索 → 分批提炼（每批 5 家）→ 落成一张新列表。

    **立即返回 running 的列表**，提炼在后台逐批执行、每批 5 行地补进列表——
    详情页的轮询会把它逐批显示出来。与「开始挖掘」并存而非替换：那条走标准
    召回，秒级、便宜；这条走 agent，分钟级、真实花钱（约 7 次百度检索 +
    数次模型调用），换来带官网与融资阶段的完整档案。标准生成的模型不可用时
    返回 503——「模型挂了」与「没找到」必须可区分（提炼阶段的模型波动由
    后台线程降级处理，不影响本次创建）。
    """
    try:
        return target_lists.create_list_from_agent(payload.profile.strip(), payload.count)
    except LlmError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"模型不可用，智能发现未执行：{error}",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_list(list_id: str, user: User = Depends(current_user)) -> None:
    if not target_lists.delete_list(list_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")


def _require_list(list_id: str) -> TargetList:
    target_list = target_lists.get_list(list_id)
    if target_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="列表不存在")
    return target_list
