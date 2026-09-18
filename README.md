# Ai-get

Ai-get 从目标客户挖掘、企业背调、智能体训练，到多渠道触达与商机洞察，串起一条完整的智能获客链路。

## 功能范围

**营销站**：首页、相关文档、服务条款、隐私政策。

**认证**：登录、注册（签发无状态令牌，演示账号开箱可用）。

**控制台**

| 模块 | 能力 |
| --- | --- |
| 潜客挖掘 | 用自然语言描述客户画像，挖掘公司或联系人，结果按列展示、可分页、可导出联系人 |
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
│   │   ├── mock/           # 演示数据语料
│   │   ├── models.py       # 请求/响应模型
│   │   └── security.py     # 令牌签发与校验
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

## 已知限制

- **无数据库**：所有数据是进程内存单例，服务重启即回到演示初始态。
- **数据不按用户隔离**：新注册的账号能看到演示账号的数据。
- 进度类接口不跑后台任务，由已用时长按比例推算，用于演示。
- 未实现参考站的积分/算力与「安装 Skill」两个模块。
