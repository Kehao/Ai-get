---
name: profile-to-weighted-criteria
description: 把一句自然语言画像（客户画像 / 理想候选人 / 供应商要求）拆解成一组**带权重的、可逐条机器判定的标准**，并输出严格 JSON。当需要「把模糊需求变成可打分、可复核的准入标准」，或要改造/移植一份「画像 → 标准」提示词时使用。触发词：画像拆解、准入标准、加权条件、资格标准、打分口径、criteria、ICP、把需求变成可判定的条件。
---

# 画像 → 加权判定标准

一句话：**把「我想要什么样的 X」变成「一组机器能逐条判定、能加权求和的 Y/N 条件」。**

这是整个「自动化筛选」链条里唯一必须由 LLM 完成的一步——语义归一化。
用户的说法千变万化（「杭州的消费品与旅游行业小微商家」），要归到**有限的标准维度**上，
规则表不可能穷举。而一旦标准生成出来，后续的检索与判定都应该交给确定性代码。

## 什么时候用

- 用户给了一段自由文本的筛选意图，需要变成结构化条件（潜客挖掘、招聘筛选、供应商准入、标的筛选）。
- 需要**可解释的匹配结论**：「为什么这家被判定为明确符合」要能逐条展示。
- 需要**可加权打分**，而不只是通过/不通过。
- 手上有一份「画像 → 标准」的 prompt，要改到新领域或新维度。

## 目录结构：真源在这里，不在代码里

```
skills/profile-to-weighted-criteria/
├── SKILL.md                      ← 你正在读的这份
├── contract.json                 ← ★ 唯一真源：维度枚举、每维度上限、expected 契约、条数区间
├── prompts/
│   ├── criteria.system.md        ← system 模板（含 $占位符，契约表由 contract.json 渲染进来）
│   └── criteria.user.md          ← user 模板
├── scripts/
│   └── validate_criteria.py      ← 独立校验器，默认读上一级 contract.json
├── examples/
│   ├── README.md                 ← 样例索引与用法
│   ├── valid/                    ← 5 份真实调用快照（只有输入 + 输出），应当全部通过校验
│   ├── invalid/                  ← 12 份反面样本，每份只针对一条契约规则，必须被拒
│   └── porting/                  ← 移植示例（B2B → 招聘），说明「只换一个文件」为什么不够
└── references/
    ├── prompt.md                 ← 渲染结果快照（逐字）+ 移植指南 + 调用参数
    └── pitfalls.md               ← 实测踩坑清单（11 条）
```

**只有一份提示词。** 运行时不内嵌 Python 副本，也不在 markdown 里手抄一份契约表——
同一段文字有两份副本必然漂移，而「这批标准是哪版 prompt 产出的」要写进任务记录，
漂移会让溯源失效。

| 文件 | 角色 | 谁读它 |
| --- | --- | --- |
| `contract.json` | 契约单一来源：枚举、上限、`lenient`、`expected_kind`、`enum_values`、条数区间 | 运行时渲染器 **与** 独立校验器 |
| `prompts/*.md` | 提示词骨架，只有 `$占位符` 没有具体枚举值 | 运行时渲染器 |
| `scripts/validate_criteria.py` | 白名单校验，纯标准库、无网络、无副作用 | 人 / CI / 调用方自测 |
| `references/prompt.md` | 渲染后的**逐字快照**，供人工阅读与移植对照 | 人 |

## 核心设计原则（照抄这一条就不会跑偏）

> **LLM 只负责把非结构化文本变成结构化判断；控制流、检索、算分全部归确定性代码。**

由此推出三条硬约束，任何改动都不能破坏：

| 约束 | 为什么 |
| --- | --- |
| **单次调用**，不要做成 agent 循环 | 一次生成、结果冻结，之后不再重掷。成本可预测、延迟可预测 |
| **输出必须过白名单校验** | 下游判定器**直接解析**结构化字段，不校验就会在远处崩 |
| **结果要冻结进任务记录** | 同一批结论自始至终用同一份标准，否则「为什么匹配」不可复核 |

## 工作流

1. **定维度枚举与权重表。** 先想清楚「有哪些可判定的维度」，每维度的默认权重是多少。
   权重不是均分的——画像的骨架（地域、行业）应当高于锦上添花的偏好。
   枚举写进 `contract.json` 的 `categories`；**默认权重不写在这里**，它是规则引擎的表，见下文。
2. **为每个维度定 `expected` / `tokens` 契约。** 这是全流程最容易出错的地方：
   模型很擅长写「一段描述」，但它必须产出**下游能直接解析的结构**。
   契约写成 `expected_kind` + `enum_values`，由渲染器生成表格塞进 prompt，并逐条说明反例。
3. **跑一次真实画像，人工看输出。** 重点不是「像不像人话」，而是
   ① 字段格式是否严格符合契约；② 有没有**凭空添加画像里没说的维度**。
4. **加校验器，任何一条不合规就整批降级。** 见 `scripts/validate_criteria.py`。
   逐条校验而非整批全废；但**通过数量不足时整批弃用**——半份标准比没有更危险。
5. **把产出方冻结进记录**：哪条路径、哪个 prompt 版本、哪个模型产出的。降级是静默的，不标出来
   用户只会看到「标准变了」却不知道原因。版本号就是 `contract.json` 的 `version` 字段。

## 输出契约

```json
{"criteria": [
  {"category": "industry", "name": "行业：企业服务与软件", "weight": 5,
   "question": "该公司的主营业务是否属于企业服务或软件？",
   "tokens": ["SaaS", "saas", "企业服务", "软件", "云服务"],
   "expected": "企业服务与软件", "lenient": false, "note": ""}
]}
```

| 字段 | 约束 |
| --- | --- |
| `category` | 必须是 `contract.json` 的枚举之一，**不得越界**。越界项由校验器拦下 |
| `name` | 人类可读，「维度：取值」，简短（≤ 22 个汉字） |
| `question` | 判定口径，一句话，以问号结尾 |
| `weight` | 整数 1–5。达阈值的算**硬性标准**（不满足则不允许「明确符合」） |
| `tokens` | 用于**子串匹配**的短关键词数组。不要写句子、不要写描述 |
| `expected` | **含义随 category 变化**，由该维度的 `expected_kind` 决定（见下表） |
| `lenient` | 宽松项：判定为「不确定」而不是「不符合」 |
| `note` | 可选，说明判定依据或缺失的数据 |

### `expected_kind` 四型

| `expected_kind` | 取值形状 | 校验规则 |
| --- | --- | --- |
| `text` | `"杭州"` / `"企业服务与软件"` | 非空字符串即可（供展示） |
| `range` | `"0:50"` | 必须是两个整数用**英文**冒号连接，且下界 ≤ 上界 |
| `enum` | `"A轮"` | 必须落在该维度声明的 `enum_values` 里 |
| `empty` | `""` | 必须恰好是空字符串（取值靠 `tokens` 表达） |

## 典型实例

`examples/` 下有 **5 份真实调用快照**（`valid/`）+ **12 份反面样本**（`invalid/`）+ 一份移植示例。
每份样例只保留**输入**（`profile` / `user_conditions`）与**输出**（`criteria`）。
「输入 → 最重要的输出」的对照表与逐条解读见 **`examples/README.md`**，这里只列「想学什么该看哪份」：

| 想看什么 | 打开 |
| --- | --- |
| 最标准的输出长什么样 | `valid/01-hangzhou-consumer-tourism.json`（四维度写全，5 条） |
| 怎么做到「不凭空添加维度」 | `valid/02-shenzhen-crossborder-logistics.json`（画像只说两件事，就只输出两维） |
| 枚举类维度怎么写才规范 | `valid/03-shanghai-biotech-cro.json`（`funding.expected` 逐字落在 `"B轮"`） |
| 用户手写条件会被怎么处理 | `valid/04-beijing-saas-user-conditions.json` —— **同时是反面教材**，`_issues` 记了三个真实缺陷 |
| 时间窗条件目前为什么判不了 | `valid/05-chengdu-greentech-timewindow.json` |
| 校验器到底拦得住什么 | `invalid/`（12 份，每份只触发一条规则，全部应当被拒） |
| 换领域要改哪些地方 | `porting/`（B2B → 招聘的完整对照 + 一致性守卫的实测报错） |

> **`valid/` 里的样例不要拿来做字面回归。** 模型非确定性：同一句画像连跑三次标准名就会变
> （见 `references/pitfalls.md` 第 3 条）。要比结构（维度集合、条数区间、`expected_kind`），
> 不要比文案。每份样例当次的调用次数与 token 数记在 `examples/README.md` 的对照表里。

一条命令自查全部样例的退出码是否符合预期：

```bash
cd skills/profile-to-weighted-criteria
for f in examples/valid/*.json;   do python3 scripts/validate_criteria.py "$f" >/dev/null || echo "✗ 应通过却失败：$f"; done
for f in examples/invalid/*.json; do python3 scripts/validate_criteria.py "$f" >/dev/null && echo "✗ 应拒绝却漏过：$f"; done
```

## 契约是唯一真源：改一个文件，两处跟随

`contract.json` 声明结构，**运行时渲染器与独立校验器都读它**。因此：

- 改契约表 → 只改 `contract.json`，提示词里的表格与校验器的判定规则**同时**更新，不会各说各话。
- 旧的「改脚本顶部的契约常量」做法已经废弃：那正是提示词与校验器漂移的来源
  （模型按新枚举输出、校验器按旧枚举拒绝，表现为「全都降级」的假故障）。

### 哪些值**不**在 contract.json 里（有意为之）

`CATEGORY_WEIGHTS`、`HARD_WEIGHT_THRESHOLD`、`FUNDING_KEYWORDS` 属于**规则引擎自己的表**
（`server/app/qualification/criteria.py`），由运行时在渲染时注入模板，技能目录不另存一份。

于是存在两个维护面，加载时会**逐项断言**它们一致（`_check_contract_consistency`）：

| 断言 | 不一致的后果 |
| --- | --- |
| 枚举集合 == `criteria._LLM_CATEGORIES` | 模型按新维度输出、判定器不认 |
| `funding.enum_values` == `FUNDING_KEYWORDS` 的阶段序列 | 融资阶段标准被逐条拒绝 → 整批降级 |
| 每维度 `max` == `criteria._MAX_PER_CATEGORY` | 条数上限形同虚设 |

不一致时抛 `PromptAssetError`，**加载即失败**。这不是防御性编程——它是
「改了契约表却忘了改另一处」唯一能被立刻发现的地方。

### 失败策略：起不来，而不是悄悄降级

提示词与契约是**仓库资产**，不是会抖动的外部依赖。缺失或自相矛盾属于「检出损坏」，
必须在加载时立刻炸掉并指出缺了哪个文件。若容忍它降级到规则引擎，
所有人都会以为 LLM 正在工作，而实际上提示词根本没被读到。

## 被谁消费

### 运行时（参考实现：Ai-get `server/app/llm/prompts.py`）

```python
from app.llm import load_asset, render_user_prompt, prompt_version, prompt_dir_label

asset = load_asset()                              # 读盘 + 渲染 + 缓存，含一致性断言
asset.system                                      # 渲染好的 system 提示词
render_user_prompt("杭州的消费品与旅游行业小微商家", ("必须是一年内新成立",))
prompt_version()                                  # → "criteria/v1"，写进任务记录
```

- 默认目录 `skills/profile-to-weighted-criteria`，**相对路径以仓库根为基准**。
- 换领域时用环境变量 `AIGET_LLM_PROMPT_DIR=/path/to/other-skill` 指向别处，不必改代码。
- `prompt_dir_label()` 返回**配置里写的那串字符**（不展开绝对路径），供界面展示——
  排查「这批标准用的哪份提示词」时，看配置值比看一长串绝对路径有用。
- 缓存：首次调用读盘，之后走进程内缓存；改完文件需重启（或调 `reset_cache()`）。

### 独立校验（`scripts/validate_criteria.py`）

```bash
python3 scripts/validate_criteria.py criteria.json          # 也可从 stdin 读
python3 scripts/validate_criteria.py criteria.json --json   # 机器可读输出
python3 scripts/validate_criteria.py criteria.json --contract /path/to/contract.json
```

- 纯标准库、无网络、无副作用。退出码：`0` 全合规 / `1` 有不合规项 / `2` 输入或契约不可读。
- 契约默认取脚本同级目录的上一级（`scripts/` → 技能根）的 `contract.json`。
- 校验通过的条目才允许入库；**不合规则整批降级**到确定性兜底实现。
- ⚠️ **校验对象是「模型原始输出」，不是运行时最终列表。** `reachability` 由代码统一补
  （见 `contract.json` 的 `excluded_categories`），拿补完的列表去跑校验一定报越界——
  那不是 bug，是设计意图。调试时先把 `reachability` 摘掉再校验。
- 已用真实模型输出与 11 类典型违规样本做过回归：能拦住
  `expected` 写成「50 人以下」、`weight` 给成字符串 `"3"`、宽松项给了 `false`、
  越界输出 `reachability`、某维度超出条数上限等。

## 迁到新领域：改这两处，别动那两处

| 必须改 | 说明 |
| --- | --- |
| ① `contract.json` 的 `categories` | 换成新场景的维度枚举（招聘：城市/职能/年限/学历/技能/信号；供应商：地域/品类/资质/规模/交付能力） |
| ② 规则引擎的 `CATEGORY_WEIGHTS` / `_MAX_PER_CATEGORY` / `_LLM_CATEGORIES` | 与 ① 成对改，否则一致性断言会拦下来（这正是它存在的意义） |

| 绝不能改 | 为什么 |
| --- | --- |
| ③「不要凭空添加画像里没有的维度」 | 这条是准确性的地基，换什么场景都成立 |
| ④「只输出 JSON」+ 白名单校验 | 结构化输出是「输出可校验」的前置条件，正则抠 JSON 不可靠 |

### 关于维度枚举的硬性要求

**枚举里的每个维度都必须能被现有数据判定。** 否则会出现「画像提了、模型也正确表达了、
但判定器判不了」的死路——这时应该做的是**补数据源字段**，而不是把标准删掉。

真实教训：`funding` 只能表达「融资阶段」，表达不了「**近 6 个月**完成融资」这种时间窗。
应当在 schema 里给维度加 `window`（时间窗）与 `judgeable`（能否用现有数据判定）字段，
让模型可以把「不可判定」当成一个**结论**输出，而不是默默降级成宽松项。

**改 `contract.json` 的任何语义都必须同步 bump `version`。** 标准会被冻结进任务记录，
只有知道「这批标准是哪版产出的」，改了 prompt 之后历史结论才对得上。

## 完整提示词与调用参数

渲染后的逐字提示词（system / user 两段，可直接复制）、默认权重表、
以及调用参数建议（`temperature` / `response_format` / `max_tokens` / 缓存键 / 超时）
见 **`references/prompt.md`**。
注意那份是**快照**：它是渲染结果，改契约请改 `contract.json` + `prompts/*.md`，再重新取快照。

## 实测踩坑清单（这些是花钱和时间换来的）

见 **`references/pitfalls.md`**（11 条）。最值得先读的四条：

1. **`expected` 格式必须严格**——`size` 写成「50 人以下」而不是 `"0:50"`，下游直接解析失败。
2. **宽同义词表是一把双刃剑**——它提升召回，但会把「弱命中」升级成「明确符合」。
   实测中一家法律咨询机构因为简介里有「线上**订阅**」二字，被判成「提供订阅制服务」，分数虚高 13 分。
3. **`temperature=0` 不等于可复现**——同一句输入连跑三次，产出名不同。冻结设计只能保证
   一个任务内部恒定，跨任务「同输入同结果」不成立。
4. **用户手写条件的「并入」逻辑会与 LLM 打架**（第 11 条）——否定条件可能被当成肯定证据、
   甚至把要排除的词并进「符合」的判据里。**同一个坑在判定器侧还有第二处**（第 2 条与第 4 条）：
   `lenient` 未命中给 0.5 而非 0、单 token 弱命中给满分。改标准生成解决不了这两处，**改判定才行**。
