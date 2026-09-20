# Ai-get

Ai-get 从目标客户挖掘、企业背调、智能体训练，到多渠道触达与商机洞察，串起一条完整的智能获客链路。

## 功能范围

**营销站**：首页、相关文档、服务条款、隐私政策。

**认证**：登录、注册（签发无状态令牌，演示账号开箱可用）。

**控制台**

| 模块 | 能力 |
| --- | --- |
| 潜客挖掘 | 用自然语言描述客户画像，挖掘公司或联系人，结果按列展示、可分页、可导出联系人；列表详情页提供「挖掘 / 详情」双面板：前者可编辑寻找对象与判断条件、查看挖掘策略与进度并追加结果，后者展示点击企业后的详细档案与准入条件评估 |
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
| 存储 | 进程内存（无数据库） |

## 目录结构

```text
.
├── AGENTS.md           # 仓库工作规则（Clean Code）
├── rules/              # 语言与领域专属规范
├── server/             # FastAPI 后端
│   ├── app/
│   │   ├── routers/        # 路由层
│   │   ├── repositories/   # 内存仓库
│   │   ├── qualification/  # L0 资格标准 + L3 判定
│   │   ├── providers/      # 数据源契约与演示源
│   │   ├── llm/            # LLM 接入（OpenAI 兼容，可关）
│   │   ├── mock/           # 演示数据语料
│   │   ├── models.py       # 请求/响应模型
│   │   └── security.py     # 令牌签发与校验
│   ├── .env.example        # 配置模板（复制成 .env）
│   └── requirements.txt
├── web/                # Vite + React 前端
│   └── src/
│       ├── pages/          # 页面（营销 / 认证 / 控制台）
│       ├── layouts/        # 营销布局与控制台布局
│       ├── components/     # 通用组件
│       ├── styles/         # 设计令牌与主题调色板
│       ├── api/            # 接口封装
│       └── store/          # 登录态与偏好设置
└── screenshots/        # 验收截图
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

**演示账号**：`qiukehao388@126.com` / `m831027`

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
| `AIGET_DATA_SOURCE` | `mock` | 数据源 id，见 `GET /api/targets/sources` |
| `AIGET_LLM_ENABLED` | `false` | 是否用 LLM 生成准入标准（L0） |
| `AIGET_LLM_BASE_URL` | `https://api.deepseek.com` | 任何 OpenAI 兼容端点 |
| `AIGET_LLM_MODEL` | `deepseek-flash` | 必须用服务端认可的名字 |
| `AIGET_LLM_API_KEY` | 空 | 密钥，只在 `.env` 里 |
| `AIGET_LLM_TIMEOUT_SECONDS` | `30` | 超时即降级，不阻塞任务创建 |
| `AIGET_LLM_MAX_TOKENS` | `4096` | 输出上限；截断会导致整批标准降级 |
| `AIGET_LLM_JUDGE_ENABLED` | `false` | L3 逐条判定的 LLM 兜底，调用量大 |
| `AIGET_LLM_PROMPT_DIR` | `skills/profile-to-company-criteria` | 提示词技能目录；相对路径以**仓库根**为基准。换领域时指向另一份技能即可，不必改代码 |

### 准入标准由谁生成

画像会被 L0 解析成一组带权重的判断标准。这条路径是 **LLM 优先、规则引擎兜底**：

- 开了 LLM 且调用成功 → `criteria_source = "llm"`，标签形如 `LLM · criteria/v1 · deepseek-flash`；
- 没开 LLM，或调用失败/输出没通过校验 → `criteria_source = "rule"`，标签 `内置规则引擎`，
  并在 `criteria_fallback_reason` 里写明原因。

降级是**静默**的——任务照样建得出来，只是标准质量不同。因此产出方会**冻结进任务记录**
（`criteria_source` / `criteria_label` / `criteria_fallback_reason`），列表页与详情页都会标出来。
当前状态可查 `GET /api/llm/status`（含累计调用数、缓存命中数、最近一次失败原因；**不含密钥**）。

### 提示词放在哪

L0 的提示词与它的机器可读契约放在 **`skills/profile-to-company-criteria/`**，
后端在运行时读取并渲染（`server/app/llm/prompts.py` 只是加载器，不内嵌提示词正文）。
该目录同时被独立校验器 `scripts/validate_criteria.py` 读取，因此
「模型按什么契约输出」与「校验器按什么契约拒绝」永远同源。详见该目录的 `SKILL.md`。

目录缺文件或契约与规则引擎的表不一致时，**加载即抛 `PromptAssetError`**——
提示词是仓库资产，缺失属于检出损坏，宁可起不来也不静默降级成「LLM 看起来在工作」。

> DeepSeek 官方 API 的模型名是 `deepseek-flash` 与 `deepseek-v4-pro`，
> 别名 `deepseek-chat` 等价于 `deepseek-flash`。产品宣传名（如 `DeepSeek-V4.1-Flash`）
> 不能直接当 `model` 传，会返回 `invalid_request_error`。

## 已知限制

- **无数据库**：所有数据是进程内存单例，服务重启即回到演示初始态。
- **数据不按用户隔离**：新注册的账号能看到演示账号的数据。
- 进度类接口不跑后台任务，由已用时长按比例推算，用于演示。
- 未实现参考站的积分/算力与「安装 Skill」两个模块。
