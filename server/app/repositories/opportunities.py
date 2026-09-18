"""商机洞察的数据组装。

参考账号因为没有连接渠道、也没有跑过触达，各指标为 0；复刻站点预置了一份演示数据，
使页面上的图表、动态与商机列表都可见、可筛选。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..models import ActivityItem, ChartPoint, KpiCard, OpportunityItem, OpportunityPage
from ..mock.catalog import OPPORTUNITY_SEEDS

LEVELS: tuple[str, ...] = ("建议跟进", "初步信号", "暂无信号")


@dataclass(frozen=True, slots=True)
class _RangeProfile:
    key: str
    label: str
    days: int
    scale: float
    point_count: int


RANGE_PROFILES: tuple[_RangeProfile, ...] = (
    _RangeProfile(key="7d", label="近 7 天", days=7, scale=1.0, point_count=7),
    _RangeProfile(key="30d", label="近 30 天", days=30, scale=2.6, point_count=10),
    _RangeProfile(key="12m", label="近 12 个月", days=365, scale=14.0, point_count=12),
)

_BASE_INTERACTION = 12
_BASE_MESSAGE = 34
_BASE_CONNECTION = 8
_BASE_OPPORTUNITY = 6
_DAILY_INTERACTION_SHAPE: tuple[int, ...] = (0, 1, 3, 2, 4, 1, 1)


def build_page(range_key: str) -> OpportunityPage:
    profile = _profile(range_key)
    now = datetime.now(timezone.utc)
    items = _build_items(now)
    level_counts = {level: sum(1 for item in items if item.level == level) for level in LEVELS}
    analyzed = round((1 - level_counts["暂无信号"] / max(1, len(items))) * 100)

    return OpportunityPage(
        range_label=profile.label,
        today_mined_count=3,
        today_task_label="今天已开发 3 位客户",
        follow_up_label="2 条商机等待跟进",
        kpis=[
            KpiCard(key="interaction", label="互动", value=_scaled(_BASE_INTERACTION, profile), caption="已联系或接待的客户数"),
            KpiCard(key="message", label="消息", value=_scaled(_BASE_MESSAGE, profile), caption="已发送或回复的消息"),
            KpiCard(key="connection", label="人脉", value=_scaled(_BASE_CONNECTION, profile), caption="新增 LinkedIn 人脉"),
            KpiCard(key="opportunity", label="商机", value=_scaled(_BASE_OPPORTUNITY, profile), caption="值得优先跟进的线索"),
        ],
        chart=_build_chart(profile, now),
        activity=_build_activity(items, now),
        analyzed_percent=analyzed,
        level_counts=level_counts,
        opportunities=items,
    )


def _profile(range_key: str) -> _RangeProfile:
    return next((item for item in RANGE_PROFILES if item.key == range_key), RANGE_PROFILES[0])


def _scaled(base: int, profile: _RangeProfile) -> int:
    return int(round(base * profile.scale))


def _build_chart(profile: _RangeProfile, now: datetime) -> list[ChartPoint]:
    scale = profile.point_count / len(_DAILY_INTERACTION_SHAPE)
    points: list[ChartPoint] = []
    for index in range(profile.point_count):
        shape_index = int(index / scale) % len(_DAILY_INTERACTION_SHAPE)
        interaction = _DAILY_INTERACTION_SHAPE[shape_index] + (1 if index % 3 == 0 else 0)
        points.append(
            ChartPoint(
                label=_point_label(profile, index, now),
                interaction=interaction,
                opportunity=max(0, interaction - 1 if index % 2 else interaction // 2),
            )
        )
    return points


def _point_label(profile: _RangeProfile, index: int, now: datetime) -> str:
    if profile.key == "12m":
        month = now - timedelta(days=(profile.point_count - 1 - index) * 30)
        return f"{month.month} 月"
    step = profile.days / profile.point_count
    moment = now - timedelta(days=(profile.point_count - 1 - index) * step)
    return f"{moment.month:02d}/{moment.day:02d}"


def _build_items(now: datetime) -> list[OpportunityItem]:
    items: list[OpportunityItem] = []
    for index, seed in enumerate(OPPORTUNITY_SEEDS):
        created = now - timedelta(hours=index * 5 + 2)
        items.append(
            OpportunityItem(
                id=f"opportunity-{index}",
                company_name=seed.company_name,
                contact_name=seed.contact_name,
                channel=seed.channel,
                signal=seed.signal,
                level=seed.level,
                last_message_at=created,
                summary=seed.summary,
            )
        )
    return items


def _build_activity(items: list[OpportunityItem], now: datetime) -> list[ActivityItem]:
    follow_ups = [item for item in items if item.level == "建议跟进"]
    activity: list[ActivityItem] = [
        ActivityItem(
            id=f"activity-{index}",
            title=f"{item.company_name} · {item.signal}",
            detail=item.summary,
            happened_at=item.last_message_at,
        )
        for index, item in enumerate(follow_ups[:4])
    ]
    activity.append(
        ActivityItem(
            id="activity-summary",
            title="智能体运行状态正常",
            detail=f"当前有 {len(items)} 条商机记录，其中 {len(follow_ups)} 条处于建议跟进状态，建议在今日内完成首轮跟进。",
            happened_at=now - timedelta(minutes=30),
        )
    )
    return activity
