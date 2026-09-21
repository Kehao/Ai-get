<h1 align="center">Ai-get —— AI B2B 销售智能体平台</h1>

<p align="center">
  <a href="https://get.kehao.info"><img src="https://img.shields.io/badge/live--demo-brightgreen?style=flat" alt="Live Demo"></a>
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=white" alt="React 18">
  <img src="https://img.shields.io/badge/Vite-6-646CFF?style=flat&logo=vite&logoColor=white" alt="Vite 6">
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Pydantic-v2-E92063?style=flat&logo=pydantic&logoColor=white" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/LLM-DeepSeek-4D6BFF?style=flat" alt="LLM DeepSeek">
  <img src="https://img.shields.io/badge/数据源-百度AI搜索·爱企查·Tavily·PDL-FF6A00?style=flat" alt="数据源">
</p>

<p align="center"><b>自然语言画像 → 双管线挖掘（规则召回 + LLM 智能发现）→ 智能体深挖档案 → L3 规则判定 → 智能触达与商机洞察。LLM 优先、规则兜底，降级留痕，开箱即用。</b></p>

<p align="center">
  <a href="https://get.kehao.info">在线预览</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#架构与工作原理">架构与工作原理</a> ·
  <a href="#改成你自己的">改成你自己的</a> ·
  <a href="#部署">部署</a>
</p>

> Ai-get 把「找到对的公司」到「联系上对的人」串成一条链路：<br>
> - **普通挖掘**走规则管线：百度 AI 搜索 + 爱企查召回，秒级出结果、量大管饱；<br>
> - **智能发现**走 LLM 管线：模型读网页提炼实体（每轮 5 家逐批落行），逐家深挖出完整档案；<br>
> - 所有行都过同一份 **L3 规则判定**，综合结果、匹配分、逐条依据全程可解释；<br>
> - 前端「挖掘 / 详情」双面板 + 滚动骨架 + 勾选气泡框批量深挖，过程全程可见。

## 快速开始

```bash
# 0. 克隆项目并进入项目根目录
git clone https://github.com/Kehao/Ai-get.git ai-get && cd ai-get

# 1. 后端：创建虚拟环境并安装依赖
cd server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 2. 配置（数据源与 LLM Key 都在这里）
cp .env.example .env      # 按需填入 AIGET_BAIDU_SEARCH_API_KEY / AIGET_LLM_API_KEY 等

# 3. 启动后端（:8000，接口文档 /docs）
.venv/bin/python -m uvicorn app.main:app --port 8000 --reload

# 4. 前端：装依赖并启动 Vite 开发服务器（:5173，/api 已代理到后端）
cd ../web
npm install
npm run dev               # 浏览器打开 http://localhost:5173
```

**演示账号**：`admin@admin.com` / `admin123`

## 你能做什么

开箱即用，至少这几条链路跑得通：

- **聊即挖掘**：输入「近 6 个月完成融资的 SaaS 公司」→ 智能发现分批落行（每批 5 家、滚动骨架逐批显示），行行带 AI 摘要与匹配分
- **双管线互补**：普通挖掘秒级召回工商照面字段；智能发现能挖到「藏在 36氪 / 融资报道里」的公司——媒体页里的实体模型直接认出来
- **深挖档案**：勾选行 → 气泡框「批量深挖」→ 逐家抓官网 / 子页 / 补缺检索，产出产品 / 商业模式 / 投资方 / 官网联系方式 / 企业 logo 完整档案（进行中的行整行栅格化）
- **全程可解释**：每行的综合结果都能点开「准入条件评估」——逐条标准 ✓ / ✗ / 待确认 + 权重 + 依据链接
- **LLM 不可用也不瘫**：标准生成与判定都是 LLM 优先、规则兜底，降级原因冻结进任务记录并标出
- **企业背调**：按公司名产出贸易网络 / 供应商 / 合规风险等数据卡片
- **触达闭环**：训练智能体 → 关联邮件 / LinkedIn / WhatsApp → 商机洞察看漏斗与 KPI

## 架构与工作原理

### 架构总览

```
┌──────────────────┐   HTTP/SSE    ┌──────────────────────┐   L0 标准生成    ┌──────────────────────┐
│  web/            │ ────────────▶ │  server/app/routers  │ ──────────────▶ │  server/skills/      │
│  React+TS+Vite   │               │  FastAPI  :8000      │               │  提示词技能+契约.json  │
│  (:5173 dev)     │ ◀──────────── │  repositories 仓库层  │ ◀───────────── │  (contract.json 真源) │
└──────────────────┘   JSON        └──────────┬───────────┘   标准白名单校验  └──────────────────────┘
                                              │
                    ┌─────────────────────────┼──────────────────────────┐
                    ▼                         ▼                          ▼
        ┌───────────────────────┐  ┌──────────────────────┐  ┌───────────────────────────┐
        │ providers/ 数据源      │  │ agents/ 智能发现      │  │ qualification/ 判定        │
        │ 百度AI搜索·爱企查·     │  │ 检索→分批提炼→深挖     │  │ L3 规则判定（纯规则零成本） │
        │ Tavily·PDL（按key注册）│  │ v2: L1/L2/L2.5/L3    │  │ 结果+依据写回每一行         │
        └───────────────────────┘  └──────────────────────┘  └───────────────────────────┘
                    │                         │
                    ▼                         ▼
        ┌───────────────────────────────────────────────────────┐
        │  SQLite（mining_lists / mining_rows / source_cache）   │
        │  列表状态写穿 + 启动水合：重启后列表仍在                │
        └───────────────────────────────────────────────────────┘
```

**一句话链路**：画像进 L0 生成判断标准 → 数据源/agent 召回候选 → L3 规则判定打分 → 行写穿 SQLite → 前端双面板呈现；深挖补全档案后**自动重判**刷新综合结果。

### 智能发现 agent（`server/app/agents/company_discovery/`）

进阶机制——与普通挖掘共用 L0/L3，但召回与档案由 agent 完成：

- **检索**：画像原文即查询（不拼行业词，保证「同一画像 + 不同标准」结果可复现）；
- **分批提炼**：每轮最多 5 家新实体（已找到名单避重），最多 6 轮，每批落行一次；
- **深挖 v2**：L1 抓已知链接 → L2 定位官网抓首页 → L2.5 官网子页探索（链接抽取 + 关键词挑子页）→ L3 缺什么搜什么，每级由模型整理成结构化档案；
- **回写**：行名升级为工商规范名（legal_name 优先）、企业 logo、官网联系方式状态，随后自动重判。

## 目录结构

| 目录/文件 | 角色 | 设计要点 |
|---|---|---|
| `server/app/agents/company_discovery/` | 智能发现 agent 包 | 检索 / 提炼 / 深挖 / 编排各一个模块，详见目录内 README |
| `server/app/routers/` | FastAPI 路由层 | 控制台全部 REST 接口 |
| `server/app/repositories/` | 仓库层 | 内存单例 + 列表状态写穿 SQLite，重启水合 |
| `server/app/qualification/` | L0 标准解析 + L3 判定 | 会社与找人两套并列；纯规则零成本 |
| `server/app/providers/` | 数据源层 | 官方 SDK 按 key 自动注册；`web_fetch.py` 网页抓取（零新增依赖） |
| `server/app/llm/` | LLM 接入 | OpenAI 兼容；加载器不内嵌提示词正文 |
| `server/skills/` | L0 提示词技能 | `contract.json` 是契约唯一真源，与白名单校验逐项断言一致 |
| `server/tests/` | pytest | 全部假 client，离线可跑 |
| `web/src/pages/` | 控制台页面 | 挖掘 / 背调 / 智能体 / 触达 / 洞察 |
| `web/src/components/` | 通用组件 | Button / Modal / Skeleton 骨架屏 / ChipScroller 等，全自建零 UI 库 |
| `web/src/styles/` | 设计令牌 | 主题调色板集中管理，浅/深色双主题 |

## 改成你自己的

| 想改什么 | 改哪里 |
|---|---|
| 切换数据源（换百度之外） | `.env` 改 `AIGET_DATA_SOURCE` / `AIGET_COMPANY_SOURCE`；新源 = 实现契约 + `is_configured()`，key 就绪自动注册 |
| 切换 LLM（换 DeepSeek 之外） | `.env` 改 `AIGET_LLM_BASE_URL` / `AIGET_LLM_MODEL` / `AIGET_LLM_API_KEY`（任何 OpenAI 兼容端点） |
| 改准入标准生成风格 | `server/skills/profile-to-*-criteria/` 改提示词与 `contract.json`（契约是唯一真源，改错启动即报错） |
| 调判定权重与规则 | `server/app/qualification/criteria.py` / `person_criteria.py` |
| 加智能发现档案字段 | `server/app/agents/company_discovery/spec.py` 的字段表 + `deep_dive.py` 的检索链 |
| 改前端主题 / 视觉 | `web/src/styles/` 设计令牌；组件样式 CSS Modules 就近放置 |
| 加页面模块 | `web/src/pages/` 加页面 + `web/src/api/` 加接口封装 |

## 部署

架构上是**纯前端静态站 + 一个 Python 常驻服务**，当前跑在阿里云 ECS：

```
┌────────────────────────┐   HTTP/HTTPS   ┌──────────────────────┐   uvicorn   ┌──────────────────────┐
│  静态前端 dist/         │ ─────────────▶ │  nginx :80/:443      │ ──────────▶ │  FastAPI :8000       │
│  /var/www/ai-get-www   │ ◀────────────  │  get.kehao.info      │             │  systemd 托管         │
└────────────────────────┘                └──────────────────────┘             └──────────────────────┘
```

- **机器**：ECS `i-bp10qalh50to546miwbf`，代码 clone 在 `/opt/ai-get`（GitHub 为主源）；
- **前端**：node 构建 → `/var/www/ai-get-www`；
- **后端**：uv venv（Python 3.13）+ systemd `ai-get-api.service`（失败自启、开机自启）；
- **HTTPS**：certbot 签发 + 自动续期；

**更新流程**：本机 `git push` 后，在服务器执行：

```bash
/opt/ai-get/update.sh
```

脚本会：拉取最新代码（GitHub 连接失败自动重试 5 次，全败则保持线上版本不动）→
安装前端依赖 → 构建前端 → 部署静态产物 → 重启后端 → 健康检查。
