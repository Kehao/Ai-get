---
name: profile-to-company-criteria
description: 企业画像（找公司）的「画像 → 加权判定标准」提示词资产。把一句自然语言的企业画像（如「杭州的消费品与旅游行业小微商家，员工 50 人以下」）拆成一组带权重、可逐条机器判定的标准，并输出严格 JSON。适用于潜客挖掘、销售资格筛选、标的准入等任何「把模糊需求变成可打分条件」的场景；提示词与契约自包含，可接入任意 LLM。触发词：画像拆解、准入标准、加权条件、资格标准、打分口径、ICP。
---

# 画像 → 加权判定标准（企业画像版）

一句话：**把「我想要什么样的企业」变成「一组机器能逐条判定、能加权求和的 Y/N 条件」。**
语义归一化是筛选链条里唯一必须由 LLM 完成的一步——用户的说法千变万化，要归到有限的标准维度上；
标准一旦生成，检索与判定都交给接入方的确定性代码。

与个人画像版 `profile-to-person-criteria`（本项目内）**并列、不共用契约**：判机构还是判自然人，
维度不重叠——本契约看行业、规模、融资；人物契约看姓名、职位、职级。两份 SKILL.md 章节一一对应。

## 目录结构

```
contract.json                  ← ★ 唯一真源：维度枚举、每维上限、expected 契约、条数区间、版本号
prompts/criteria.system.md     ← system 模板（只含 $占位符，发请求前按下表填充）
prompts/criteria.user.md       ← user 模板（$query + $conditions_block，每次请求填充）
```

**只有一份提示词**：枚举与权重不手抄进 markdown——由 `contract.json` 与下方权重表渲染注入，
两份副本必然漂移。

## 快速使用（三步）

**① 渲染 system 提示词。** 把 `prompts/criteria.system.md` 里的占位符按 `contract.json` 填充：

| 占位符 | 填什么 | 本契约的当前值 |
| --- | --- | --- |
| `$category_count` | 维度个数 | 6 |
| `$category_list` | 维度枚举，用「 / 」连接 | geo / industry / size / funding / business / signal |
| `$default_weights` | 各维默认权重（见下） | `geo=5、industry=5、size=3、funding=3、business=3、signal=2、reachability=1` |
| `$contract_table` | 契约表：每个维度一行 `\| category \| tokens \| expected \|`，expected 列按契约的 `expected_hint` 渲染（`$enum_values` 替换为该维枚举值） | 见 contract.json |
| `$per_category_rule` | 由每维 `max` 生成：「每个 category 最多一条；只有 business、signal 允许各最多 3 条」 | 同左 |
| `$lenient_categories` | `lenient: true` 的维度名 | business 与 signal |
| `$hard_weight_threshold` | 硬性权重阈值 | 3 |
| `$min_criteria` / `$max_criteria` | 输出条数区间 | 2 / 8 |

**② 发送请求。** system 用渲染结果；user 按 `prompts/criteria.user.md` 填 `$query`（画像原文）与
`$conditions_block`（用户手写补充条件，每行一条 `- 条件`，没有则为空）。建议参数：
`temperature=0`、JSON 输出格式、`max_tokens` ≥ 4096（上限是防截断，不是目标）。

**③ 校验输出。** 模型只返回 `{"criteria": [...]}`；接入方必须做**白名单校验**后再入库：

- `category` ∈ 契约枚举；`weight` 为 1–5 整数；`name` ≤ 22 汉字；`question` 以问号结尾
- `expected` 按该维 `expected_kind` 校验：`text` 非空 / `range` 为 `"最小:最大"` 英文冒号且下界 ≤ 上界 / `enum` 落在契约枚举内 / `empty` 恰为 `""`
- `lenient` 与契约声明一致（宽松维必须 true，其余必须 false）；每维条数 ≤ `max`；总条数在区间内
- 不合规条目逐条剔除；**通过数 < 2 时整批弃用**——半份标准比没有更危险

## 输出契约（单条标准）

```json
{"category": "industry", "name": "行业：企业服务与软件", "weight": 5,
 "question": "该公司的主营业务是否属于企业服务或软件？",
 "tokens": ["SaaS", "saas", "企业服务", "软件", "云服务"],
 "expected": "企业服务与软件", "lenient": false, "note": ""}
```

| 字段 | 约束 |
| --- | --- |
| `category` | 必须是契约枚举之一 |
| `name` | 人类可读，「维度：取值」，≤ 22 个汉字 |
| `question` | 判定口径，一句话，以问号结尾 |
| `weight` | 整数 1–5；达到阈值为**硬性标准**，判「不符合」则结论不得为「明确符合」 |
| `tokens` | 用于**子串匹配**的短关键词数组，不要写句子 |
| `expected` | 含义随 category 变化，由该维 `expected_kind` 决定 |
| `lenient` | 宽松项：未命中判「不确定」而不是「不符合」 |
| `note` | 可选，说明判定依据或缺失的数据 |

## 契约是唯一真源：改一个文件

改维度、取值格式、每维条数上限 → **只改 `contract.json`**，提示词表与校验逻辑同时跟随
（校验规则从契约派生，不要另存一份枚举副本）。改契约的任何语义必须同步 bump `version`。

## 硬性不变量（改契约时不能破坏）

1. **不要凭空添加画像里没有的维度**——准确性的地基，换什么场景都成立。
2. **只输出 JSON + 白名单校验**——下游判定器直接解析结构化字段，不校验就会在远处崩。
3. **单次调用、结果冻结**——不做 agent 循环；同一批结论自始至终用同一份标准，否则「为什么匹配」不可复核。
4. **枚举里每个维度都必须能被现有数据判定**——否则应补数据源字段，而不是删标准
   （真实教训：`funding` 表达不了「近 6 个月完成融资」这种时间窗）。
5. **`reachability` 不让模型产出**——与画像内容无关，任何画像都适用，由接入方统一补。

## 已知教训（实测换来的）

- `expected` 格式必须严格：`size` 写成「50 人以下」而不是 `"0:50"`，下游直接解析失败。
- 宽同义词表是双刃剑：提升召回，但会把弱命中升级成「明确符合」（一家法律咨询机构因简介里有
  「线上订阅」被判成「提供订阅制服务」，分数虚高 13 分）。
- `temperature=0` 不等于可复现：同一句输入连跑三次标准名就会变——比结构，不要比文案。
- 用户手写条件的「并入」逻辑会与 LLM 打架（否定条件可能被并进正向判据）；判定器侧的
  打分实现也要同步审视（宽松项未命中的记分、单关键词弱命中给满分是两类常见偏差）。

## 移植到新领域

改 `contract.json` 的 `categories`（换维度枚举）+ ①表中的权重与阈值 → 即可迁到招聘、供应商准入等场景；
硬性不变量 1、2 与「只输出 JSON」不能改。
