"""服务端集中配置。

所有对外可见的数量选项、时长与分页边界都收在这里，避免魔法数字散落在业务代码中。

`.env` 在模块导入时就加载，因此**任何模块只要先 import 本模块，环境变量就已经就绪**——
包括 `app.llm.config`。这是刻意的顺序：配置只有一个入口。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 本文件位于 server/app/config.py，因此 .env 在 server/.env。
# override=False：已存在的真实环境变量优先于 .env，便于 CI 或容器注入。
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_FILE, override=False)

SERVICE_NAME = "Ai-get API"
SERVICE_VERSION = "1.0.0"

# 令牌签名密钥。演示环境用固定默认值，使服务重启后已签发的令牌依然有效。
SECRET_KEY = os.environ.get("AIGET_SECRET_KEY", "ai-get-demo-secret-key")
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60

# 挖掘任务从创建到完成的模拟耗时（秒）。进度由创建时间推算，因此无需后台线程。
MINING_DURATION_SECONDS = 15
RESEARCH_DURATION_SECONDS = 12

# 挖掘任务的状态推进配比。三段之和为 1，与上游 Websets 的
# generating_criteria → searching → verifying 保持一致。
#
# searching 只占 0.18：召回在真实链路里是**一次**接口调用，而 verifying 要对每个候选
# 逐条判定标准，是整条链路里最慢的一段。配比照着真实耗时分配，进度条才不会骗人。
MINING_PHASE_WEIGHTS = {
    "generating_criteria": 0.12,
    "searching": 0.18,
    "verifying": 0.70,
}

# 默认数据源 id。接入真实数据源后，用环境变量切过去即可，业务代码无需改动。
DEFAULT_DATA_SOURCE = os.environ.get("AIGET_DATA_SOURCE", "mock")

# ── 真实数据源凭据（P4/P5）─────────────────────────────────────────────────
# 留空 = 该源不注册，业务链路自动退回 mock，不会报错。
# Tavily（P4 召回）：https://tavily.com 免费层每月 1000 credits。
# PDL（P5 字段补齐）：https://peopledatalabs.com 免费层每月 100 credits，
# 仅 base 字段（联系方式档位要付费，免费层拿不到就如实显示缺失）。
TAVILY_API_KEY = os.environ.get("AIGET_TAVILY_API_KEY", "")
PDL_API_KEY = os.environ.get("AIGET_PDL_API_KEY", "")

# 真实源按次计费，同一企业的查询结果必须落缓存：TTL 内重复命中零成本。
# P7 的持久化缓存落地后，这里只是把存储介质从进程内字典换成 SQLite。
SOURCE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

COMPANY_COUNT_OPTIONS = (25, 100, 500, 1000)
DEFAULT_COMPANY_COUNT = COMPANY_COUNT_OPTIONS[0]

# 触达渠道清单。工作空间设置的默认渠道与智能体模板共用同一份来源。
OUTREACH_CHANNELS = ("邮件", "LinkedIn", "WhatsApp")

DEFAULT_WORKSPACE_NAME = "Ai-get 工作空间"

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
