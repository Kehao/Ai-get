# Ai-get

Ai-get 是一个 AI B2B 销售智能体平台：从**目标客户挖掘**、**企业背调**、**智能体训练**，
到**多渠道触达**与**商机洞察**，串起一条完整的智能获客链路。

> 线上地址：`https://get.kehao.info`（演示账号 `admin@admin.com` / `admin123`）

## 两种挖掘模式

潜客挖掘有两条并行的产出管线，共用同一套准入标准（L0 生成）与判定标准（L3 规则）：

| | 普通挖掘 | 智能发现（agent） |
| --- | --- | --- |
| 原理 | 规则管线：百度 AI 搜索泛搜索 → 站点三分类过滤 → 爱企查补量 → 字段富化 | LLM 管线：检索 → **模型提炼实体**（每轮 5 家，逐批落行）→ **逐家深挖** |
| 能挖到谁 | 只认「像企业站的页」 | 媒体页、目录页里提到的公司都能认出来 |
| 档案深度 | 爱企查工商字段 + 网页摘要 | 官网 + 子页整理的完整档案（产品 / 商业模式 / 投资方 / 官网联系方式 / 企业 logo） |
| 速度成本 | 秒级、便宜 | 分钟级、花模型调用（提炼 + 深挖） |
| 适用 | 快速扫一圈、量大管饱 | 挖「藏在报道里」的公司、要完整档案 |

**智能发现管线**（`server/app/agents/company_discovery/`，详细说明见该目录 README）：

1. **检索**：画像原文作为查询（不拼行业词），百度 AI 搜索返回网页正文；
2. **提炼**：模型读正文提取实体，每轮最多 5 家新实体（已找到名单避重），最多 6 轮，
   每批落一批行、前端滚动骨架逐批显示；
3. **深挖**（对单家企业，勾选行后在气泡框里批量逐个发起，进行中的行整行栅格化）：
   - L1 抓已知链接 → L2 定位官网并抓首页 → L2.5 官网子页探索（链接抽取 → 关键词挑子页）→ L3 按缺失字段定向检索；
   - 每级结束由模型整理一次，产出**结构化档案**；
4. **回写与重判**：行名升级为工商规范名（legal_name 优先）、企业 logo、官网联系方式状态，
   并按 L3 规则标准**重判**，刷新综合结果与匹配分。

## 功能范围

**营销站**：首页、相关文档、服务条款、隐私政策。

**认证**：登录、注册（签发无状态令牌，演示账号开箱可用）。

**控制台**

| 模块 | 能力 |
| --- | --- |
| 潜客挖掘 | 自然语言描述客户画像，两种模式挖掘公司或联系人；列表详情页提供「挖掘 / 详情」双面板：前者可编辑寻找对象与判断条件、查看挖掘策略与进度，后者展示企业详细档案（深挖状态 + 档案字段 + 富化台账 + 智能调研 + 准入条件评估）；支持筛选、排序、分页、导出联系人、勾选气泡框批量深挖 |
| 企业背调 | 按公司名发起背调，产出贸易网络/供应商/合规风险等数据卡片与结论文本 |
| 训练智能体 | 配置销售智能体的画像、触达渠道与话术策略 |
| 关联账号 | 连接邮件、LinkedIn、WhatsApp 等触达渠道 |
| 知识库 | 抓取官网内容生成问答条目，供智能体作答时引用 |
| 商机洞察 | 触达漏斗与 KPI 走势，按时间范围切换 |

**账户体系**：账户菜单提供主题与语言的快速开关、用户中心、设置与退出登录；设置项（工作空间名称、默认渠道、结果数量、通知开关）通过接口持久化。

**主题**：浅色 / 深色 / 跟随系统三档，运行时即时切换，首屏无闪烁。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vite 6 + React 18 + TypeScript + Less（CSS Modules）+ React Router |
| 图标 | lucide-react |
| 后端 | FastAPI + Pydantic v2 + Uvicorn |
| 存储 | 进程内存 + SQLite（挖掘列表状态、数据源缓存落库；`companies` / `company_enrichments` 两张表已建 DDL 但代码未接入，见 `server/schema/README.md`） |
| LLM | OpenAI 兼容端点（默认 DeepSeek），LLM 优先、规则兜底，降级留痕 |
| 数据源 | 百度 AI 搜索（含爱企查）、Tavily、Peopledatalabs——官方 SDK，按 key 自动注册 |

## 目录结构

```text
.
├── AGENTS.md           # 仓库工作规则（Clean Code）
├── rules/              # 语言与领域专属规范
├── doc/                # 概念文档（预留）
├── server/             # FastAPI 后端
│   ├── app/
│   │   ├── agents/         # 智能发现 agent（company_discovery 包，含 SKILL README）
│   │   ├── routers/        # 路由层
│   │   ├── repositories/   # 仓库层（内存单例 + 列表状态写穿 SQLite）
│   │   ├── qualification/  # L0 资格标准 + L3 判定（会社与人物两套并列）
│   │   ├── providers/      # 数据源契约、网页映射与各数据源实现（含 web_fetch 网页抓取）
│   │   ├── llm/            # LLM 接入（OpenAI 兼容，可关）
│   │   ├── mock/           # 演示数据语料（策略组、档案构建等）
│   │   ├── models.py       # 请求/响应模型
│   │   └── security.py     # 令牌签发与校验
│   ├── skills/             # L0 提示词技能（contract.json 是契约唯一真源）
│   ├── schema/             # SQLite DDL 与说明
│   ├── tests/              # pytest（全部用假 client，零网络）
│   ├── .env.example        # 配置模板（复制成 .env）
│   └── requirements.txt
├── web/                # Vite + React 前端
│   └── src/
│       ├── pages/          # 页面（营销 / 认证 / 控制台）
│       ├── layouts/        # 营销布局与控制台布局
│       ├── components/     # 通用组件（含 Skeleton 骨架屏）
│       ├── styles/         # 设计令牌与主题调色板
│       ├── api/            # 接口封装
│       └── store/          # 登录态与偏好设置
├── screenshots/        # 验收截图
└── .ref/               # 第三方站快照（本地参考用，不入版本控制）
```

## 本地运行

**后端**（默认 `http://localhost:8000`，接口文档在 `/docs`）

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000 --reload
```

**前端**（默认 `http://localhost:5173`，已把 `/api` 代理到后端）

```bash
cd web
npm install
npm run dev
```

**演示账号**：`admin@admin.com` / `admin123`

## 配置

所有配置走环境变量，来源统一是 `server/.env`（由 `app.config` 在导入时加载）。
复制模板即可开始：

```bash
cp server/.env.example server/.env
```

`.env` 已被 `.gitignore` 排除，密钥只放在这里。**改完 `.env` 需要重启后端进程**，
它是进程级单例，不会热加载。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `AIGET_DATA_SOURCE` | `mock` | 数据源 id，见 `GET /api/targets/sources`；生产用 `baidu` |
| `AIGET_LLM_ENABLED` | `false` | 是否用 LLM 生成准入标准（L0） |
| `AIGET_LLM_BASE_URL` | `https://api.deepseek.com` | 任何 OpenAI 兼容端点 |
| `AIGET_LLM_MODEL` | `deepseek-flash` | 必须用服务端认可的名字 |
| `AIGET_LLM_API_KEY` | 空 | 密钥，只在 `.env` 里 |
| `AIGET_LLM_TIMEOUT_SECONDS` | `60` | 超时即降级，不阻塞任务创建 |
| `AIGET_LLM_MAX_TOKENS` | `4096` | 输出上限；截断会导致整批标准降级 |
| `AIGET_LLM_JUDGE_ENABLED` | `false` | L3 逐条判定的 LLM 兜底，调用量大 |
| `AIGET_LLM_PROMPT_DIR` | `skills/profile-to-company-criteria` | 企业模式的提示词技能目录；**相对路径以 `server/` 为基准**。换领域时指向另一份技能即可，不必改代码 |
| `AIGET_LLM_PERSON_PROMPT_DIR` | 空 | 「找人」模式的提示词技能目录，留空即用 `skills/profile-to-person-criteria` |
| `AIGET_COMPANY_SOURCE` | 空 | 公司召回的专用源，留空跟随 `AIGET_DATA_SOURCE`。网页检索源没有人物能力，两个键必须分开 |
| `AIGET_TAVILY_ENABLED` | 空 | 置 `false` 时 Tavily 即便 key 就绪也不注册（密钥不用删，改回即恢复） |

### 准入标准由谁生成

画像会被 L0 解析成一组带权重的判断标准。这条路径是 **LLM 优先、规则引擎兜底**：

- 开了 LLM 且调用成功 → `criteria_source = "llm"`，标签形如 `LLM · criteria/v2 · deepseek-flash`
  （版本号取自 `contract.json`，找人模式是 `person-criteria/v2`）；
- 没开 LLM，或调用失败/输出没通过校验 → `criteria_source = "rule"`，标签 `内置规则引擎`，
  并在 `criteria_fallback_reason` 里写明原因。

降级是**静默**的——任务照样建得出来，只是标准质量不同。因此产出方会**冻结进任务记录**
（`criteria_source` / `criteria_label` / `criteria_fallback_reason`），列表页与详情页都会标出来。
当前状态可查 `GET /api/llm/status`（含累计调用数、缓存命中数、最近一次失败原因；**不含密钥**）。

### 提示词放在哪

L0 的提示词与它的机器可读契约放在 **`server/skills/profile-to-company-criteria/`**，
找人模式则用并列的 **`server/skills/profile-to-person-criteria/`**（两份契约互不共用）。
后端在运行时按 `AIGET_LLM_PROMPT_DIR` 读取并渲染，
而 `server/app/llm/prompts.py` 只是加载器，不内嵌提示词正文。

`contract.json` 是契约的**唯一真源**：提示词的契约表由它渲染，白名单校验
（`server/app/qualification/criteria.py` 与 `person_criteria.py`）也按它拒绝，
且加载时会**逐项断言**它与规则引擎自己的表一致，因此
「模型按什么契约输出」与「校验器按什么契约拒绝」永远同源。详见各自目录的 `SKILL.md`。

目录缺文件或契约与规则引擎的表不一致时，**加载即抛 `PromptAssetError`**——
提示词是仓库资产，缺失属于检出损坏，宁可起不来也不静默降级成「LLM 看起来在工作」。

> DeepSeek 官方 API 的模型名是 `deepseek-flash` 与 `deepseek-v4-pro`，
> 别名 `deepseek-chat` 等价于 `deepseek-flash`。产品宣传名（如 `DeepSeek-V4.1-Flash`）
> 不能直接当 `model` 传，会返回 `invalid_request_error`。

## 已知限制

- **存储不是纯内存**：`server/schema/` 下的 5 张表里，`source_cache` / `mining_lists` /
  `mining_rows` 已在用（列表状态写穿 + 启动水合、缓存跨进程生效），
  所以挖掘列表在服务重启后仍可回看；`companies` / `company_enrichments` 只有 DDL，
  代码尚未接入。**账号与偏好设置**等仍是内存单例，重启回初始态。
- **数据不按用户隔离**：新注册的账号能看到演示账号的数据。
- 进度类接口不跑后台任务，由已用时长按比例推算，用于演示。
- 未实现参考站的积分/算力与「安装 Skill」两个模块。
