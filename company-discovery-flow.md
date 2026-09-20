# 公司发现的数据流程（端到端）

> 一句话画像到「带联系人的目标列表」之间，数据到底经过了哪些手。
> 层号沿用 `company-discovery-plan.md` 的 L0–L4；召回层的概念与边界见 `recall-layer.md`；
> 数据源选型与实测缺陷见 `p6-implementation-plan.md`。

## 0. 全景

```
用户输入「找 SaaS 公司」+ 数量 25
   │
   │  POST /api/targets/lists ──────────────── routers/targets.py
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ repositories/targets.py::create_list()      ← **真实工作全在这一步同步做完**│
│                                                                      │
│  ① L0 _build_criteria()      画像 → criteria[]（LLM 优先/规则兜底）  │
│  ② L1 _recall()              向数据源要候选 → CompanyRecord[]        │
│  ③ L2 enrich_companies()     瀑布补齐缺失字段（失败即原样返回）      │
│  ④ L3 _build_rows()          逐条判定 → Judgment → 列表行 + 分数     │
│  ⑤ 条件项 / 策略文案 / 冻结标准来源                                   │
└──────────────────────────────────────────────────────────────────────┘
   │
   │  list_store.save() 写穿 mining_lists / mining_rows（SQLite）
   ▼
返回 status="running" 的 TargetList
   │
   │  前端轮询 GET /lists/{id} / /companies
   ▼
_refresh() 按**已用时长**推进 phase → 列表逐行「验证完成」→ completed
   │
   ▼
详情页：GET /companies/{row_id}（档案卡 + 准入条件评估 + 来源）
联系人：GET /companies/{row_id}/contacts
```

**要记住的一句话**：`create_list` 是同步的——接口返回时召回和判定都已经做完了。
`running` 与进度条是为了演示补的动画，不是真实的后台任务（见 §7）。

## 1. 三个入口

| 入口 | 路由 | 主要差别 |
| --- | --- | --- |
| 新建挖掘 | `POST /api/targets/lists` | 画像原文 → 全套 L0–L3 |
| 上传名单 | `POST /api/targets/lists/upload` | 用**固定画像** `_UPLOAD_QUERY` 生成标准，再把名单里的公司名作为 `names=` 交给召回（同名企业在检索里比画像更准） |
| 列表内写操作 | `/more`、`/conditions`、`/mine` | 见 §8，各自只重跑一部分 |

## 2. L0：画像 → 加权标准

唯一入口 `_build_criteria(mode, query, user_conditions)`——它是整个仓库里**唯一**决定
「用哪套标准引擎」的地方（会社走 `qualification/criteria.py`，人物走 `person_criteria.py`，
两套维度不重叠）。

- **LLM 优先、规则兜底**：调用成功 → `criteria_source="llm"`；没开或失败/输出不过白名单校验
  → `"rule"`，原因写进 `criteria_fallback_reason`。
- 降级是**静默**的，所以产出方会**冻结进任务记录**（`criteria_source` / `criteria_label` /
  `criteria_fallback_reason`），由 `_stamp_criteria_source()` 盖章。新增「重建标准」的入口
  也必须盖章。
- 产物 `Criterion`：`id / name / question / category / weight / tokens / expected / lenient`。
  会社维度权重：`geo 5 · industry 5 · size 3 · funding 3 · business 3 · signal 2 · reachability 1`。
- **一次挖掘 1 次 LLM 调用**，与召回多少家无关。这条性质要保住。

## 3. L1：召回

```
_recall(mode, query, limit, seed, criteria, names, exclude_keys)
   └─ company_hints(criteria)  ← 提示词从**冻结的标准**派生，不重解析画像
        └─ CompanyQuery(text, limit, preferred_city, industry_hints, names, seed)
             └─ call_source(company_source(), "company_search", …)
                  └─ registry：计时 / 计价 / 异常收敛成 SourceError
                       └─ 数据源 search_companies()
```

- **提示词**：`company_hints` 取 geo 条件的城市 + industry 条件的 tokens。
  城市**只走 `preferred_city`，不拼进查询文本**。
- **数据源**（当前 `AIGET_COMPANY_SOURCE=baidu`）：两阶段检索＝泛搜索拿企业官网 →
  数量不足时用爱企查站点限定补量，两段按注册域/名称合并去重。
- **映射**（`providers/web_mapping.py`，与 Tavily 共用）：站点三分类（企业站保域名 /
  目录站保记录丢域名 / 媒体站整条丢）、取名闸门（取不出名称的记录直接丢弃——
  名称是判定层唯一的抓手）。
- **缓存**：`providers/cache.py` 落在 SQLite `source_cache` 表，键形如
  `baidu:search:{检索文本}:{limit}`，TTL 7 天。空串哨兵表示「源确认过没有」。
- 出口：`list[CompanyRecord]`，已按 `exclude_keys` 剔除追加时要避开的行。

## 4. L2：字段补齐（瀑布）

`enrich_companies(records)`：没注册补齐源就**一次调用都不发**，直接原样返回。
有源时 `collect("company_enrich", …)` 按 priority 逐级兜底，然后：

- `merge_enrichment` **只填空字段**（`summary / location / employees / funding_stage` 为空才补），
  并合并 evidence、打 `enriched_by`；
- `missing_fields` **如实上报**——缺失是数据源的事实，不伪造；
- 全部失败 → 保留召回结果，缺字段交给前端「重试该字段」链路。

## 5. L3：逐条判定

`_judge_record(mode, criteria, record)` → `judge(criteria, record)`：

1. 标准为空 → `empty_judgment()`（「待确认」，**不假装通过**）；
2. 对每条标准调对应 handler（`geo / industry / size / funding / business / reachability`，
   未知维度退化到 business）；
3. `score_verdicts`：`ratio = Σ(weight × factor) / Σweight`，其中
   `ratio ≥ 0.75` → **明确符合**，`≥ 0.45` → **可能符合**，否则 **待确认**；
   任一**硬性条件**（`weight ≥ 3` 且非 lenient）判「不符合」→ 一票否决，最高只能到「可能符合」；
4. `_compose_reason` 生成「为什么匹配」文案，每条 verdict 带 `references`（来源标题 + URL）。

⚠️ lenient 维度（`business` / `signal`）未命中记 0.5 而不是 0——「公开资料没写到」
不等于「不存在」。

## 6. 行构建

`_build_rows` 把记录 + 判定翻成列表行（会社/人物两种形状，只有 row id、判定、
创建时间的生成规则共用）：

| 行字段 | 来源 |
| --- | --- |
| `company_name` / `website` / `industries` | `CompanyRecord`（`domain` → `website`） |
| `ai_summary` | `CompanyRecord.summary` |
| `match_level` / `match_reason` / `score` | **全部来自 `Judgment`**（可复核的前提） |
| `summary_state` / `contact_state` / `official_contact_state` | `missing_fields` 里有没有对应字段 |
| `location` / `employees` / `funding_stage` | 记录字段（多为 L2 补齐来的） |
| `custom_values` | 用户自定义列 |

分页/筛选/排序在 `page_companies` → `_sort_rows`（排序键只吃已落库的字段）。

## 7. 进度与持久化

**进度是插值的，不是真实进度**：`_refresh` 按 `elapsed / MINING_DURATION_SECONDS` 推进
`generating_criteria → searching → verifying → completed`，计数**只从已落库的判定结果里算**
（`qualified` = 非「待确认」，`full` = 「明确符合」）。真实链路里「验证」本来就最慢，
与其先塞一批未判定的候选，不如让「已验证」的口径保持干净。

持久化（`repositories/list_store.py`）：`save()` 是**写穿**——UPSERT 列表 + 整体替换行，
启动时 `load_all()` 水合回内存，对路由/分页/导出零感知。

- 序列化分工：pydantic 模型走 `model_dump_json`；dataclass（`Criterion` / `Judgment` /
  `CompanyRecord`）走 `app.serialize` 按注解编解码。
- **崩溃语义**：水合时 `running` 一律按 `completed` 处理（行已经全判完了，
  中断的只是前端动画；假装还在跑只会让进度条卡在 99%）。

## 8. 列表内的四个写入口

| 操作 | 路由 | 重跑什么 | LLM 调用 |
| --- | --- | --- | --- |
| 追加结果 | `POST /lists/{id}/more` | 只 `_recall`（`exclude_keys` 避开已有行）→ 追加行 | 0 |
| 保存配置 | `PATCH /lists/{id}/conditions` | `_build_criteria(query, cleaned)` + **`_rejudge`**（就地重判已有行，不换企业） | +1 |
| 重跑挖掘 | `POST /lists/{id}/mine` | 重建标准（**必须带 `condition_items` 的文本**，否则用户条件全丢）→ 换一批结果 → 进度归零 | +1 |
| 字段重试 | `POST /lists/{id}/companies/{row_id}/retry` | 会社：`contacts` 真的再调一次 `contact_search`；`summary`/`official_contact` 目前本地重生成。人物：**明确拒绝**（数据源没有「按人补字段」能力） | 0 |

两个必须守住的点：**保存配置要就地重判**（标准改了却留旧评估，详情页会和列表页自相矛盾）；
**重跑必须带用户条件**（只按 query 重建会把用户配置全部丢掉）。

## 9. 详情页那条流

`GET /lists/{id}/companies/{row_id}` → `company_detail()` 现算三类卡片
（`mock/dossiers.py`，都是**从记录与判定派生**，不是另存一份数据）：

- `build_references` —— 来源列表（证据回查）；
- `build_evaluations` —— 准入条件评估（来自 `Judgment.verdicts`）；
- `build_research_results` —— 背调结果卡。

联系人 `GET …/contacts` 从 `contact_search` 能力取（会社才有）。
触达计划 `POST /lists/{id}/outreach` 产 5 个触点，写回 `follow_up_plan`。

## 10. 存储层真实状况

⚠️ **`README.md` 与旧笔记里「无数据库、进程内存单例」的说法已经过时**。
P7 起 `server/schema/` 有 5 张表，`app/db.py` 首次连接时按文件名序号执行 DDL：

| 表 | 职责 | 状态 |
| --- | --- | --- |
| `source_cache` | 数据源结果缓存 | ✅ 在用（`providers/cache.py`，跨进程） |
| `mining_lists` | 挖掘列表主档 | ✅ 在用（写穿 + 启动水合） |
| `mining_rows` | 每次挖掘的候选行（记录 + 判定） | ✅ 在用 |
| `companies` | 企业主档：跨挖掘去重主键 | ⚠️ **只有 DDL，代码尚未接入** |
| `company_enrichments` | 补齐台账：哪个字段、哪个源、什么时候给的 | ⚠️ **只有 DDL，代码尚未接入** |

后两张是 P7 的预留（「候选缓存与去重跨会话生效」的完整形态），
写文档或读代码时别误以为公司主库已经在用。仍然成立的部分：
**数据不按用户隔离**、真实源按次计费。

## 11. 一次挖掘的调用账

| 动作 | LLM 调用 | 数据源调用 |
| --- | --- | --- |
| 新建挖掘 | 1 | 召回 1~2 次（+补齐，未配源则 0） |
| 保存配置 | 1 | 0 |
| 重跑挖掘 | 1 | 1~2 |
| 追加结果 | 0 | 1~2 |
| 上传名单 | 1 | 1~2 |
| 字段重试 | 0 | 仅 `contacts` 时 1 次 |

缓存命中时数据源调用归零。**调用次数与召回多少家无关**——这是要保持的性质。

## 12. 改代码前先看这几条不变量

1. **一次挖掘 1 次 LLM 调用**，与召回数无关（会社与人物各自成立）；
2. **召回宽、判定严**——发现问题时先分清是「没被带回来」还是「带回来没判对」；
3. **判定结论必须与标准同源**：改标准就要重判，改企业才叫重跑；
4. **标准是唯一真源**：召回提示从 `criteria` 派生，不重解析画像；
5. **不补数量**：数据源给多少就是多少，不许用合成条目凑数；
6. **契约同源**：`skills/*/contract.json` 是唯一真源，加载时逐项断言与规则引擎一致，
   不一致直接起不来（`PromptAssetError`）；
7. **降级必须留痕**：`criteria_source` / `criteria_fallback_reason` 要盖章，
   空值表示「没试过」而不是「成功了」。

## 13. 相关文档

- `company-discovery-plan.md`——上游（Websets / Revor）拆解与 L0–L4 分层规划；
- `recall-layer.md`——召回层是什么、边界在哪、怎么认出是它的问题；
- `llm-role.md`——LLM 坐哪三个位子、明确不做什么；
- `p6-implementation-plan.md`——数据源选型、覆盖率实测与已修缺陷；
- `server/schema/README.md`——建表 DDL 的设计约定。
