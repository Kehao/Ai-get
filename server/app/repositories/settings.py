"""工作空间设置仓库。演示环境不接数据库，设置保存在进程内存中。"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from ..config import DEFAULT_COMPANY_COUNT, DEFAULT_WORKSPACE_NAME, OUTREACH_CHANNELS
from ..models import UpdateSettingsRequest, WorkspaceSettings


class SettingsRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings = WorkspaceSettings(
            workspace_name=DEFAULT_WORKSPACE_NAME,
            default_channel=OUTREACH_CHANNELS[0],
            default_count=DEFAULT_COMPANY_COUNT,
            notify_on_reply=True,
            notify_weekly_digest=False,
            updated_at=datetime.now(timezone.utc),
        )

    def read(self) -> WorkspaceSettings:
        with self._lock:
            return self._settings.model_copy()

    def update(self, payload: UpdateSettingsRequest) -> WorkspaceSettings:
        """局部更新：只覆盖请求中显式给出的字段。"""
        with self._lock:
            changes = payload.model_dump(exclude_none=True)
            self._settings = self._settings.model_copy(
                update={**changes, "updated_at": datetime.now(timezone.utc)},
            )
            return self._settings.model_copy()
