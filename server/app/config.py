"""服务端集中配置。

所有对外可见的数量选项、时长与分页边界都收在这里，避免魔法数字散落在业务代码中。
"""

from __future__ import annotations

import os

SERVICE_NAME = "Ai-get API"
SERVICE_VERSION = "1.0.0"

# 令牌签名密钥。演示环境用固定默认值，使服务重启后已签发的令牌依然有效。
SECRET_KEY = os.environ.get("AIGET_SECRET_KEY", "ai-get-demo-secret-key")
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60

# 挖掘任务从创建到完成的模拟耗时（秒）。进度由创建时间推算，因此无需后台线程。
MINING_DURATION_SECONDS = 15
RESEARCH_DURATION_SECONDS = 12

COMPANY_COUNT_OPTIONS = (25, 100, 500, 1000)
DEFAULT_COMPANY_COUNT = COMPANY_COUNT_OPTIONS[0]

# 触达渠道清单。工作空间设置的默认渠道与智能体模板共用同一份来源。
OUTREACH_CHANNELS = ("邮件", "LinkedIn", "WhatsApp")

DEFAULT_WORKSPACE_NAME = "Ai-get 工作空间"

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
