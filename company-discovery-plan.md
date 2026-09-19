# 公司挖掘功能规划：上游实现拆解与数据源选型

> 结论先行：`revor-company-discovery` 的内部实现并不神秘，它是一层 **SaaS 编排**——把自然语言画像丢给 Revor 自研的 **Websets** 接口，由服务端自动生成加权资格标准、跑完整条「标准生成 → 全网检索 → 逐条验证」流水线，最后只回传通过验证的公司。数据源本身是可采购的；真正难复刻的是**资格标准的自动生成与证据级评分**。
>
> 对 Ai-get 的启示：**先把「标准 + 评分 + 证据」这层做出来（可以完全用假数据），再去接真实数据源**。反过来先接数据源，只会得到一个没有说服力的公司名录。

---

## 一、上游四个 Skill 的真实调用链

`Kehao/revor-skills` 实际来源是 `laiye-revor/revor-skills`（README 里的安装命令 `npx skills add laiye-revor/revor-skills`）。它不是四个独立工具，而是一条**针对同一批公司的递进流水线**，每个 Skill 都有「MCP 工具」和「本地 Node 脚本」两条等价执行路线。

| Skill | 职责 | 依赖的真实接口 | 是否产生费用 |
| --- | --- | --- | --- |
| `revor-company-discovery` | 自然语言画像 → 一批**通过资格验证**的公司 | `POST /api/v2/websets` | 是（扣 credits） |
| `revor-company-research` | 单家公司尽调：身份 + 海关 + 联系人 | `/api/v2/research/public-web`、`/api/v2/customs/*`、`/api/v2/research/contacts` | 部分是（candidates 明确标注非计费） |
| `revor-contact-search` | 按域名捞联系人 | `POST /api/v2/research/contacts` | 是 |
| `revor-outreach` | 触达前的账号就绪检查与发送 | `GET /api/v2/connect/accounts` | 否（发送走已连渠道） |

链路关系：**discovery 出一个公司列表 → 挑若干家交给 research 做尽调 → contact-search 捞人 → outreach 发送**。上游 SKILL.md 明确禁止 discovery Skill 越界做联系人查找或触达，四个 Skill 的职责边界是硬隔离的。

对 Ai-get 的意义：我们现在的「潜客挖掘 → 企业详情 → 联系人 → 触达计划」页面结构，**与上游的职责切分是一致的**，不需要重做信息架构，只需要把每一段背后的数据来源换掉。

---

## 二、Websets 的机制拆解（这是核心）

从 `scripts/revor-websets.mjs` 可以完整还原它的实现，没有黑盒：

### 2.1 请求契约

```
POST /api/v2/websets
Idempotency-Key: revor-company-discovery-{YYYY-MM-DD}-{sha256(payload)[:24]}
{
  "query": "东南亚的工业自动化设备经销商",   // ≤ 2000 字符
  "title": "东南亚自动化经销商",              // ≤ 200 字符，可选
  "count": 25,                                // 仅允许 25 / 100 / 500 / 1000
  "target_kind": "company",                   // 公司挖掘恒为 company
  "locale": "zh"                              // en | zh
}
```

三个值得注意的设计决策：

1. **`count` 是枚举而非任意值**（25/100/500/1000），并且在错误码里专门有 `membership_tier_insufficient` 和 `webset_count_not_available_for_tier`——列表规模本身就是付费档位的一部分。Ai-get 目前已经去掉了套餐概念，所以我们的 `count` 应该做成任意上限（如 1–1000）+ 服务端配额限流，而不是照抄枚举。
2. **`Idempotency-Key` 是内容哈希**（sha256 前 24 位 + 日期），意味着**同一天内完全相同的查询会命中同一个 Webset**，天然做了去重计费。这是很值得抄的一招。
3. **`query` 不鼓励过度指定**。SKILL.md 写得很直接：*"Do not invent missing constraints or turn the request into an over-specified checklist."* 因为下游会自动生成标准——用户写太细反而会互相打架。

### 2.2 三阶段状态机 + 进度回传

创建后轮询 `GET /api/v2/websets/{id}`，`status` 依次流转：

```
generating_criteria  →  searching  →  verifying  →  completed
                                                  ↘ failed / cancelled
```

轮询期间服务端回传一个 `progress` 对象，字段是：`stage`、`goal`、`verified`、`qualified`、`full`、`stop_reason`。

**这里的 `goal` / `verified` / `qualified` / `full` 四元组是对 Ai-get 最有参考价值的地方**：它说明参考站的挖掘进度条不是假的加载动画——它真的知道「本轮目标多少家、已验证多少家、其中合格多少家、完全匹配多少家」。我们现在的进度是 `create_list` 时按创建时间推算出来的（`MINING_DURATION_SECONDS` 线性插值），观感接近但语义是空的。要做真实感，这四个数字必须有真实来源——**哪怕来源是假数据，也应该让假数据在这四个维度上自洽**（例如 `qualified ≤ verified`、`full ≤ qualified`）。

### 2.3 结果读取与字段

```
GET /api/v2/websets/{id}/items?limit=10&match=qualified&detail=standard&cursor=...
```

- `match=qualified` 由服务端过滤，客户端不需要自己筛。
- `detail` 三档决定字段深度与最大分页，且**客户端会拒绝非法组合而不是静默截断**：

| detail | 最大 page_size | 返回内容 |
| --- | --- | --- |
| `compact` | 50 | 公司核心字段 + match status/score |
| `standard` | 25 | 完整公开字段 + checks + 每条标准的 status/score/weight/引用数 |
| `full` | 10 | 额外返回每条标准的推理过程与引用 URL |

- 每条 item 的关键字段是 `match.status`（只有 `full` / `partial` 两个合法值）、`score`，以及**逐条 criterion 的判定结果**。
- 防御性校验很严：分页出现重复 item、`provisional=true` 的临时结果出现在已完成 Webset 里、match status 非法——全部按 `invalid_response` 报错。

**这几条直接映射到 Ai-get 的匹配度模型**：我们现在有「明确符合 / 可能符合 / 待确认」三档，本质就是 `full` / `partial` / 未通过。差别在于**上游的每一档都挂着「哪条标准、权重多少、得分多少」**，而我们现在只有一句写死的 `_MATCH_REASONS` 文案。这是最该补的一环。

---

## 三、research Skill 暴露的三个数据域

`revor-company-research` 的接口清单，等于把参考站的单公司尽调能力完整摊开了：

| 数据域 | 接口 | 关键参数 |
| --- | --- | --- |
| 公开网页身份 | `POST /api/v2/research/public-web` | `queries`（≤2 条/批）、`search_limit`、`include_domains`、`user_location` |
| 海关/贸易 | `POST /api/v2/customs/company-candidates` | `company_name`、`company_role`(importer/exporter)、`catalog`(imports/exports)、`compare_catalogs`、`hs_code`、`origin_country_code`、`destination_country_code`、`start_date`、`end_date` |
| 贸易报告 | `POST /api/v2/customs/trade-reports`（另有 `counterparties` / `categories` / `trends` / `countries` 五个细分口径） | 同上，日期范围 ≤ 1 年 |
| 联系人 | `POST /api/v2/research/contacts` | `domain`、`positions`（如 `CEO\|Procurement\|Supply Chain`）、`limit`、`locale` |

其中**海关数据的路由规则**写得极其谨慎，值得单独记一笔：

- `company_role` 说明「被查公司在这条贸易记录里是进口方还是出口方」，`catalog` 说明「去 imports 还是 exports 数据目录里查」，**两者互相独立**。
- 典型反直觉案例：中国三一重工卖设备给印尼买家，应该是 `company_role=exporter` + `catalog=imports` + `destination_country_code=IDN`（因为印尼的进口报关单才会记录这笔交易）。
- 不允许从「进口数据 / 出口数据」这种措辞反推 catalog，只允许从业务场景默认推：采购/供应商尽调 → `importer/imports`，销售/买家发现 → `exporter/exports`。

对 Ai-get 的启示：如果我们以后要做「外贸场景挖客户」，这个角色/目录的正交建模必须原样搬过来，否则一定会把查询打到没有覆盖的数据目录上，然后误报成「无数据」。

---

## 四、Ai-get 现状盘点

必须先说清楚我们离真实有多远：

| 环节 | 现状 | 真实度 |
| --- | --- | --- |
| 挖掘入口 | `POST /api/targets/lists` → `target_lists.create_list(query, mode, count)` | 契约完整，与上游 `POST /websets` 语义等价 |
| 候选生成 | `app/mock/company_corpus.py` + `_build_rows(seed, count, columns, city)`，`seed` 来自 `list_id` | **纯模拟**，按 `list_id` 哈希确定性生成 |
| 数据源 | **一个都没有**。全项目无任何外部 API 调用 | 0 |
| 匹配判定 | `_MATCH_REASONS` 三档固定文案 + `_MATCH_LEVEL_ORDER` 排序 | 文案级，无标准、无权重、无得分 |
| 资格标准 | `build_conditions(query)` 只做标点切句 + 截断 22 字 + 补 2 条兜底 | 是**文本切片**，不是标准 |
| 进度 | 由 `started_at` 与 `MINING_DURATION_SECONDS` 推算 | 时间插值，非真实进度 |
| 持久化 | 内存单例，重启即回到初始态 | 无 |

也就是说：**Ai-get 的挖掘是「长得像」而不是「是」**。这不是问题——前端演示完全可以这样，但一旦要接真实数据，上面五层都得动。

---

## 五、规划建议：四层数据架构

不要指望一个数据源包打天下。B2B 公司数据的现实是**没有一个源是全覆盖的**（Apollo 强在北美中小企业、ZoomInfo 强在北美中大型、企查查/天眼查是中国大陆的唯一入口、Exa/Parallel 强在长尾和语义发现），所以业界标准做法是**瀑布式（waterfall）**：按字段收录率从便宜到贵逐级补齐，先命中的源就停。

```
                     ┌──────────────────────────────────────┐
  用户画像 ─────────▶ │  L0  资格标准引擎（LLM）              │
  "找东南亚自动化      │  query → 加权 criteria[] + 判定规则   │
    设备经销商"        └──────────────┬───────────────────────┘
                                      │ criteria
                     ┌────────────────▼───────────────────────┐
                     │  L1  候选召回（宽召回，宁滥勿缺）        │
                     │  语义检索 API / 企业库全文检索 / 工商库  │
                     └──────────────┬───────────────────────┘
                                      │ 候选公司（可能几百条）
                     ┌────────────────▼───────────────────────┐
                     │  L2  字段补齐（瀑布式，逐级兜底）        │
                     │  域名字段 → 规模/行业/融资 → 联系方式     │
                     │  去重与实体消解（域名 + 名称 + 国家）     │
                     └──────────────┬───────────────────────┘
                                      │ 完整画像候选
                     ┌────────────────▼───────────────────────┐
                     │  L3  资格验证（LLM + 证据）              │
                     │  逐条 criteria 判 full/partial + score   │
                     │  输出「为什么匹配」+ 引用来源             │
                     └──────────────┬───────────────────────┘
                                      │
                     ┌────────────────▼───────────────────────┐
                     │  L4  可选增强：海关/贸易、新闻、招投标     │
                     └────────────────────────────────────────┘
```

**关键：L0 和 L3 是护城河，L1/L2/L4 是采购项。** 上游 Revor 把 L0/L3 做成了自有能力（"Revor automatically generates weighted qualification criteria"），L1/L2 则对接各路数据商。我们复刻时如果把顺序搞反，会有大量精力耗在数据采购谈判上，而产品最难解释的「为什么这家公司匹配」反而没做。

### 5.1 代码落点建议

当前后端是 `routers/` + `repositories/` + `mock/` 三层。接真实数据源应该**新增 `providers/` 一层，而不是改 `repositories/`**：

```
server/app/
├── providers/
│   ├── base.py          # Protocol: CompanySource / ContactSource / TradeSource
│   ├── mock.py          # 包住现有 company_corpus，演示模式继续可用
│   ├── semantic.py      # L1：Exa / Tavily / Parallel
│   ├── firmographic.py  # L2：Apollo / People Data Labs / 企查查
│   └── waterfall.py     # 瀑布编排 + 字段级兜底
├── qualification/
│   ├── criteria.py      # L0：query → 加权标准
│   └── judge.py         # L3：逐条判定 + 打分
└── repositories/targets.py   # 只负责状态机与持久化，不再生成数据
```

这样做的收益：`MockProvider` 与真实 Provider 实现同一个 Protocol，前端契约不变，**可以逐层替换、随时回退**。`_build_rows` 那套确定性哈希生成逻辑完整保留在 mock provider 里，不删除。

### 5.2 状态机对齐

把现在的时间插值进度换成真实状态机，与上游一一对应：

| Ai-get 现状 | 建议目标 | 上游对应 |
| --- | --- | --- |
| 无 | `generating_criteria` | 生成加权标准 |
| `running` | `searching` | 召回候选 |
| 无 | `verifying` | 逐条验证 |
| `completed` | `completed` | 完成 |
| 无 | `failed` / `cancelled` | 失败/取消 |
| `progress`（0–100 插值） | `{goal, verified, qualified, full, stop_reason}` | 四元组进度 |

前端 `TargetsPage` 的进度条已经能展示百分比，扩展成「已验证 128 / 合格 41 / 完全匹配 27」比单一百分比更有说服力，且改动量很小。

---

## 六、数据源选型矩阵

### L1 候选召回：语义检索 / 公开网页

这一层的任务是「从一句话找到可能相关的公司域名或实体」，覆盖面优先于准确度。

| 方案 | 定位 | 价格量级 | 适合场景 |
| --- | --- | --- | --- |
| **Exa** | 语义检索、找相似站，自带公司/论文/新闻索引 | ~$7 / 1K 次 | 长尾发现，「做 X 的公司」这类模糊描述 |
| **Parallel** | `FindAll` / Entity Search，明确面向**列表构建** | 按任务计费 | 最接近「一次性给一批公司」，与 Websets 定位最像 |
| **Tavily** | Agent 原生检索，有免费层 | 免费层 + 按次 | 快速接第一个真实源、做 PoC |
| **Linkup** | 合规优先（ZDR / BYOC），检索质量高 | 按次 | 欧洲客户、有数据驻留要求的场景 |
| **Firecrawl** | 爬取 + 结构化抽取 | 按页 | 有了域名之后抓官网补字段 |
| **Brave Search API** | 独立索引 | 按次，便宜 | 通用兜底检索 |

**建议起点：Tavily（免费层验证通路）→ Exa 或 Parallel（正式做召回）。**

### L2 字段补齐：企业库

| 方案 | 覆盖 | 价格量级 | 备注 |
| --- | --- | --- | --- |
| **Apollo.io** | 3,000 万+ 公司 / 2.1 亿+ 联系人 | 免费层 + $49/用户/月起 | 性价比最高，自带邮箱与电话，北美强 |
| **People Data Labs** | 7,000 万+ 公司 | ~$0.01–0.10 / 条 | API 优先、按量计费，适合程序化补齐 |
| **Coresignal** | 企业维度字段全 | 按量 | API 优先，字段整齐 |
| **ZoomInfo** | 1 亿+ 公司，最全 | 年费级别（约 $33.5K/年起） | 企业级，中小企业不要碰 |
| **Crunchbase** | 融资 / 并购 / 投资方 | 按档订阅 | 专治「近期完成 A 轮」这类条件 |
| **LinkedIn Sales Navigator** | 会员自报数据，准确度高 | 按席位 | **无批量 API**，只能人肉操作，不适合做后端数据源 |
| **企查查 / 天眼查 / 启信宝** | 中国大陆工商实体 | 按次（约 0.02–0.15 元/次） | 中国大陆唯一权威入口，见第七节 |

### L3 交易信号：海关 / 贸易数据

只在「跨境贸易、找买家/供应商」场景才需要，成本高，不要作为默认层。

| 方案 | 覆盖 | 价格量级 |
| --- | --- | --- |
| **ImportYeti** | 美国提单 | 免费 |
| **ImportGenius** | 美国提单 | $229–1,999 / 月 |
| **Volza** | 203 个国家 | 约 $1,500 / 年 |
| **Panjiva**（S&P） | 全球，企业级 | 企业报价 |
| **Trademo / Techsalerator** | 195 国 | 按量 |

注意：这块数据本质是**各国公开报关单的整理**，所以覆盖度天然不均衡（美国最全、欧盟次之、很多国家没有）。如果做这个功能，UI 上必须像上游那样明确标注「数据覆盖限制」，否则空结果会被用户误读成「这家公司没有贸易活动」。

### L4 联系方式

Apollo / PDL 自带联系人库，可以先不单独采购。需要专门补时考虑 Hunter.io（域名找邮箱）、Prospeo、Findymail、Dropcontact。上游的做法是**只在公司身份确定后按官方域名查**，绝不用公司名去猜域名——这条规则必须照抄，否则会捞到一堆同名无关公司的邮箱。

---

## 七、中国大陆的特殊性（不能忽视）

如果 Ai-get 要覆盖中国大陆企业，Apollo / ZoomInfo / PDL 的覆盖率会**断崖式下跌**（中国大陆中小企业的公开英文信息极少）。必须走：

| 数据商 | 实体量级 | 强项 | 计费 |
| --- | --- | --- | --- |
| **企查查** | 3.5–5.8 亿 | 招投标数据、股权穿透、全球实体 | 约 0.02–0.05 元/次 |
| **天眼查** | 约 3 亿 | 司法涉诉、知识产权 | 约 0.15 元/次 |
| **启信宝** | 亿级 | 企业征信、关联图谱 | 按次/按档 |

值得注意的一点：**招投标数据是企查查独有的强项**，而「近期中标了 XX 项目」恰好是极强的采购意向信号——这是英文数据源完全没有的维度，可以作为 Ai-get 的差异化能力。

合规提醒：中国大陆的工商公示信息虽然公开，但**批量抓取与二次分发有明确边界**（《个人信息保护法》《数据安全法》），务必通过官方 API 采购而非爬取。

---

## 八、落地路线（按投入产出排序）

| 阶段 | 内容 | 依赖 | 产出 |
| --- | --- | --- | --- |
| **P0** | 抽 `providers/` 层，把现有 `company_corpus` 包成 `MockProvider`；`targets.py` 只留状态机 | 无 | 架构解耦，前端零改动 |
| **P1** | 实现 L0 资格标准引擎：`query` → 加权 `criteria[]`（含名称、权重、判定问题） | 一个 LLM 调用即可 | **前端可以立刻展示「本次挖掘依据的 N 条标准」，这是观感提升最大的一步** |
| **P2** | 实现 L3 判定器：对 mock 数据逐条判 `full/partial` + `score` + 证据文案，替换 `_MATCH_REASONS` 硬编码 | 依赖 P1 | 「为什么匹配」变成可解释的，对齐上游 |
| **P3** | 状态机对齐：`generating_criteria → searching → verifying` + `{goal, verified, qualified, full}` 四元组进度 | 依赖 P0 | 进度条从假动画变成有语义的数据 |
| **P3.5** | 召回相关性对齐：修 `select_seeds()` 无城市分支忽略行业提示的缺陷 + 扩充演示语料 | P0 | 召回命中率开始随画像变化，不再是「换个画像都是同一个数」 |
| **P4** | 接第一个真实召回源（Tavily 免费层 → Exa / Parallel），替换 `MockProvider` 的候选生成 | P0 | 真实公司、真实域名 |
| **P5** | 接企业库补齐字段（Apollo / PDL），加瀑布兜底与去重 | P4 | 字段完整度接近参考站 |
| **P6** | 中国大陆场景接企查查；跨境场景接海关数据 | P5 | 差异化能力 |
| **P7** | 持久化：加一层 SQLite 或轻量 KV 做候选缓存与去重 | P5 | 真实源有配额与成本，必须缓存，且重复查询要能命中 |

**排序理由**：P1–P3 三阶段全部基于现有 mock 数据就能完成，**不花一分钱数据费，却能拿到 80% 的观感提升**（因为参考站的「专业感」主要来自标准、评分和证据，而不是公司名本身）。P4 之后才开始产生数据成本与采购决策，此时产品形态已经验证过了。

> **P3.5 已完成（2026-09-20）。** 落地时发现 P1–P3 的观感提升被一个隐藏缺陷吃掉了：
> `select_seeds()` 在「画像里没有城市」时会**整池轮转、完全不看 `industry_hints`**，
> 于是「找消费品/旅游行业的小微商家」召回来的是一堆人工智能与工业软件公司，
> 行业标准成批落空——**表面上像判定层不准，实际是召回层没有可用的相关语料**。
> 修法与实测数据见 `llm-role.md` §7.6：语料 39 → 85 家、合成行业包 10 → 17 个，
> 消费品/旅游类画像的召回行业命中率 **24% → 100%**，且命中率从「无论什么画像都是 24%」
> 变成「随画像变化」。
>
> 注意 P3.5 与 P4 的**分工边界**：P3.5 修的是策略（相关性该按什么排序），
> 扩语料只是为了让演示数据有足够的相关条目可召回；**它不解决覆盖盲区**——
> 语料某个行业只有几家时，命中率上界就是那几家除以上限（如环保、CRO 类画像约 28%）。
> 这类缺口按 §九.6 的做法**如实标注，不要用合成条目凑数**，等 P4 接真实源后自然消失。

---

## 九、反模式清单

复刻这类产品时容易踩的坑，逐条记下：

1. **先接数据源、后做资格标准。** 顺序反了会得到一个「公司名录导出器」，而不是「智能挖掘」。
2. **用公司名猜域名去查联系人。** 同名公司极多，上游明令禁止，只允许用已验证的官方域名。
3. **把 API 报错当成空结果。** 上游的错误分类学里 `error_kind` 与「查询成功但无数据」是严格区分的事件；`external_api_billing_retryable` 绝不能被渲染成「这家公司没有贸易记录」。
4. **海关数据的角色与目录混为一谈。** 见第三节，这是最容易出错的地方。
5. **照抄 `count` 枚举（25/100/500/1000）。** 那是付费档位的产物；Ai-get 已去掉套餐概念，应该做成连续区间 + 服务端配额。
6. **在 UI 上承诺「全网覆盖」。** 每个数据源都有覆盖盲区，上游专门要求标注 coverage limitation，我们也应该照做。
7. **不做缓存。** 真实源按次计费，且同一查询必然会重复出现，没有缓存等于直接烧钱。

---

## 十、技术架构选型：MCP / 后端服务 / Agent

### 10.1 先拆问题：这三个词根本不在同一层

「抓数据做成 MCP、后台服务、还是 agent」这个问法本身把三个不同层次的东西并列了：

| 形态 | 它实际是什么层 | 它回答的问题 |
| --- | --- | --- |
| **后端服务** | 执行层 | 谁真的去调厂商 API、谁管缓存 / 配额 / 重试 / 密钥 |
| **Agent** | 决策层 | 当步骤数量事前无法确定时，谁来决定下一步查什么 |
| **MCP** | 接口层（协议契约） | 这项能力如何被**别的 LLM 宿主**调用 |

所以不是三选一。正确的问题是「**每一层分别用什么形态**」。

### 10.2 结论

**主线是后端服务；Agent 只在两个受控点上出现；MCP 是可选的对外出口。**

一句判断法：

- 调用方是**你自己的浏览器前端** → 后端服务
- 调用方是**别人的 agent 宿主**（Claude Code、WorkBuddy 等）→ MCP，且必须架在后端服务之上
- **步骤数事前不确定、需要按中间结果改变策略** → 才上 agent

按最后一条衡量：公司挖掘是一条**固定流水线**（生成标准 → 召回 → 补齐 → 判定），步骤数事前完全确定。它不符合 agent 的判据。

### 10.3 为什么抓数据绝不能做成 agent

五条硬理由，按严重程度排：

1. **成本无界。** Agent 循环的调用次数不由你决定。一次「帮我找找东南亚的自动化经销商」可能触发 3 次调用，也可能触发 40 次——而每次 L2 补齐都是按条计费的。SaaS 产品的成本必须可预测，这是最致命的一条。
2. **不可审计、不可复现。** 我们的核心卖点是「为什么这家公司匹配」（L3 的逐条证据）。Agent 的自由度会让同一 query 两次跑出不同结果，产品承诺就无法成立。
3. **密钥暴露。** 厂商 API key 一旦进入 agent 上下文，就会进日志、进模型请求。密钥只能存在于服务端进程里。
4. **缓存语义缺失。** 同一 query 必然被重复提交（上游用内容哈希做 `Idempotency-Key` 就是这个原因）。Agent 没有天然的缓存与去重语义，等于每次都重新烧钱。
5. **参考站自己就不是 agent。** 这是最有说服力的一条证据：Rover/Revor 内部就是 `POST /api/v2/websets` + 轮询三阶段状态机，纯 HTTP 编排，没有任何 agent 循环。

**而它之所以以 Skill / MCP 形态分发，是因为它的分发渠道是 agent 宿主（Claude Code），不是因为它的内部实现需要 agent。** 这一点必须想清楚：不要把自己的「分发形态」误读成「实现形态」。

反过来还有一个现成的佐证——上游的 SKILL.md 里写着：

> If `revor_create_webset` … MCP tools are available, use them. Otherwise resolve `scripts/revor-websets.mjs` … Do not recreate the API requests with curl or inline code.

同一个能力，**MCP 工具与本地 Node 脚本两条等价路线，跑的是同一套 HTTP 接口**。这就是「接口层与实现层分离」的标准范例：MCP 只是外壳，后端才是实现。

**但必须说清楚「不共用」的到底是哪一层**——这里最容易读反。准确的说法不是「revor 自己没用到这套能力」，而是：

| | 是否共用 |
| --- | --- |
| 后端实现、`/api/v2/*` 接口 | ✅ **完全共用**。Skill、MCP、Web 控制台是同一套接口的三个客户端 |
| 账户、credits、限流 | ✅ 共用（见下方证据 2） |
| 错误分类学、幂等键、分页与轮询约定 | ✅ 共用，这些约定写在后端返回里 |
| **MCP / Skill 这层外壳** | ❌ 不共用。它只为「调用方不是浏览器」的场景存在 |

三条可以直接验证的证据：

1. `revor.ai/zh/my-api-keys` 页面存在——API 是对外**产品化**的，用户自己建 key、自己消耗 credits。若 MCP 是内部实现，就不需要给用户发 key。
2. SKILL.md 里明确写着 *"Revor API and MCP access **share account-level limits**, so do not switch keys or protocols to evade a limit."* **如果 MCP 是内部实现层，就不会有「API 和 MCP 两个东西共享配额」这种表述**——正因为它们是**并列的两个对外入口**，才需要专门声明配额是打通的。
3. 客户端配置落在 `~/.config/RevorSkill/.env`、默认指向 `https://revor.ai`——这是**外部进程访问线上 SaaS** 的形态，不是产品内部模块之间调用的形态。

所以精确结论是：**revor 的产品本体（Web 控制台）不会去调自己的 MCP**（浏览器应用没有理由绕一层 JSON-RPC 协议），**但它和 MCP、和 Skill 脚本用的是同一个后端、同一套接口**。外壳层不共用，能力实现层完全共用。

### 10.4 但也不该是「一个同步接口」：需要 Job + Worker + Cache 三件套

后端服务不能只写成一个 `POST /api/discover` 同步返回。三个现实约束：

| 约束 | 后果 | 对策 |
| --- | --- | --- |
| 一次挖掘 25–1000 家、耗时数分钟 | 同步接口必然超时 | **异步 Job + 轮询**（沿用我们已有的 `running/completed` 状态机） |
| 厂商 API 按次计费、有速率限制 | 重复查询直接烧钱，超限直接失败 | **缓存 + 内容哈希幂等键**（照抄上游 `sha256(payload)[:24]` 的做法）、令牌桶限流、退避重试 |
| 多租户 + 计费 | 必须知道每次调用花了多少钱 | **调用台账**（记 provider / 条数 / 耗时 / 成本），否则无法定价也无法排查 |

进度用轮询即可，不必上 SSE——前端 `TargetsPage` 已经在轮询，且真实 job 的进度语义（`goal / verified / qualified / full`）比流式推送更重要。

### 10.5 Agent 的两个正确落点（以及一个常见误用）

Agent 不是不能用，是要用在**步骤数不确定**的地方：

1. **产品内的对话式探索面**（可选，非主线）。「帮我看看这家公司值不值得跟进」这类开放式请求，步骤数确实不确定——要查身份、查贸易、查新闻、查联系人，查完可能还要追一轮。这里适合 agent。**但它是独立入口，不能替代「挖掘」按钮的主链路。**
2. **内部离线批处理**。比如批量给两万条历史线索补字段、批量做尽调，跑在离线任务里，失败了重跑不影响在线服务。

**常见误用：把 L0 资格标准生成和 L3 逐条判定做成 agent。** 这两步都是**一次 LLM 调用**（输入 query → 输出结构化 criteria；输入 criteria + 候选 → 输出逐条判定），有明确的输入输出契约，用结构化输出（JSON schema）约束即可。做成 agent loop 只会让结果不稳定、成本翻倍，且更难保证「同一天同一 query 结果一致」。

一句话区分：**要 LLM 做「一次判断」用单次调用；要 LLM 做「不确定步数的探索」才用 agent。**

### 10.6 MCP 什么时候才需要

MCP 的适用条件是**分发渠道变了**，不是**技术栈变了**：

- ✅ 用户是「用 Claude Code / WorkBuddy 的人」，而不是「打开浏览器的人」
- ✅ 内部有多个 agent 要复用同一份能力（做一个 MCP server 比让每个 agent 各自实现一遍强）
- ❌ 不适合做浏览器产品的主链路：stdio 进程模型、天然无多租户、无配额、无持久化、无并发控制

**如果要做，它应该是一个薄适配层**——`mcp/` 目录里几十行代码，把 MCP 工具调用翻译成对内部 `providers/` 的调用，**不重复实现任何业务逻辑**。这正是上游 `revor_create_webset` 与 `revor-websets.mjs` 的关系。

### 10.7 推荐的落地形态

```
浏览器
  │  HTTP
  ▼
FastAPI · Job API ──▶ Job 状态 (SQLite)
  │  创建任务 / 查状态 / 分页        ▲  状态机 + 幂等键
  │                                  │
  ▼                                  │
Worker (asyncio) ────────────────────┘
  │  跑流程：L0 → L1 → L2 → L3，串行、可重试、可取消
  ├──▶ LLM 单次调用（生成标准 / 逐条判定）
  └──▶ providers/ · Protocol
         ├── mock        （保留，演示模式）
         ├── semantic    （Exa / Parallel / Tavily）
         └── firmographic（Apollo / PDL / 企查查）
                │
                ▼
           厂商 API

旁路（可选）：
外部 agent 宿主 ──▶ MCP 薄适配层 ──▶ 复用上面的 providers，不另起实现
```

### 10.8 从当前「无 DB」状态过去，要补什么

当前后端是纯内存单例，重启即清空。接真实数据源前，最小改动是：

| 要补的 | 最小实现 | 说明 |
| --- | --- | --- |
| **持久化** | SQLite（`sqlite3` + 线程池，或 `aiosqlite`） | 单文件、零运维，够用。存 Job 状态 + 候选缓存 + 调用台账 |
| **Worker** | `asyncio.create_task` + SQLite 状态 | **不要一上来上 Celery / Redis**，当前量级用不上 |
| **崩溃恢复** | 启动时把 `running` 的 Job 标为 `failed` 或重新入队 | 内存版没有这个问题，有持久化之后必须处理 |
| **缓存层** | `provider:query_hash:params_hash` → 结果 + 时间戳 | 挂在 provider 之下，对上层透明 |
| **配额与限流** | 令牌桶 + 每 provider 并发上限 | 厂商 API 超限是必然事件，要当作正常分支处理 |

**不要动的**：`web/` 的接口契约。因为 `providers/` 与 `repositories/` 之间是新加的层，前端完全无感——这也是 10.7 那个结构最大的价值：**任意一层都可以单独替换或回退**。

### 10.9 一句话回答

**抓数据是后端服务（Job + Worker + providers），不是 agent，也不是 MCP。** Agent 只用在「步骤数不确定」的对话式探索面；MCP 只在「要把能力分发给别人的 agent」时才做，且必须是复用后端的一层薄壳。参考站本身就是这个结构——它的 MCP/Skill 外壳与内部 HTTP 实现是分离的。

---

## 十一、一句话总结

上游 `revor-company-discovery` 的实现已经完整暴露在它自己的客户端脚本里：**一次 `POST /api/v2/websets` + 三阶段轮询 + 逐条标准判定**。它不是「更全的数据源」，而是「更严的资格标准 + 更可解释的评分」。

所以 Ai-get 的规划优先级应该是：**先把 criteria / score / 证据这三样用假数据做扎实（P1–P3），再按 L1 → L2 → L4 的顺序接真实数据源（P4–P7）**。数据源选型上，召回层用 Exa/Parallel，补齐层用 Apollo（海外）或企查查（中国大陆），交易层按需接 Volza/ImportGenius，联系人不单独采购——这套组合已经能覆盖参考站的全部能力面。

技术形态上，抓数据是**后端服务**：`Job API + Worker + providers/` 三层，配 SQLite 做持久化与缓存。Agent 只出现在「步骤数不确定」的对话式探索面，MCP 只在要把能力分发给外部 agent 时才做、且必须是复用后端的一层薄壳。**参考站自己就是纯 HTTP 编排而非 agent，它的 Skill/MCP 外壳与内部实现是分离的**——这一点是整份规划里最容易被误读、也最值得照抄的地方。
