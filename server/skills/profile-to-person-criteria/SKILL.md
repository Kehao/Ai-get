---
name: profile-to-person-criteria
description: 个人画像的「画像 → 加权判定标准」提示词资产。把一句自然语言的个人画像（如「找云安全公司的 CMO，最好新上任」）拆成一组带权重、可逐条机器判定的人物标准，并输出严格 JSON。适用于招聘筛选、销售线索的个人挖掘、专家检索等任何「把模糊的人物需求变成可打分条件」的场景；提示词与契约自包含，可接入任意 LLM。触发词：个人画像、候选人标准、人物画像拆解、招聘资格条件。
---

# 画像 → 加权判定标准（个人画像版）

一句话：**把「我想要什么样的人」变成「一组机器能逐条判定、能加权求和的 Y/N 条件」。**
判的对象是自然人（候选人 / 联系人），不是企业——画像里的企业名与行业词描述的都是
「这个人所属的机构」或「他做什么职能」，不要产出企业规模、融资这类人物档案上不存在的标准。

与企业画像版（本项目内为 `profile-to-company-criteria`）**并列、不共用契约**：判自然人还是判机构，
维度不重叠——本契约看姓名、职位、职级；企业契约看行业、规模、融资。两份 SKILL.md 章节一一对应。

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
| `$category_count` | 维度个数 | 7 |
| `$category_list` | 维度枚举，用「 / 」连接 | name / title / company / seniority / geo / background / signal |
| `$default_weights` | 各维默认权重（见下） | `name=5、title=4、company=4、seniority=3、geo=3、background=3、signal=2、reachability=1` |
| `$contract_table` | 契约表：每个维度一行 `\| category \| tokens \| expected \|`，expected 列按契约的 `expected_hint` 渲染（`$enum_values` 替换为该维枚举值） | 见 contract.json |
| `$per_category_rule` | 由每维 `max` 生成：「每个 category 最多一条；只有 background、signal 允许各最多 2 条」 | 同左 |
| `$lenient_categories` | `lenient: true` 的维度名 | background 与 signal |
| `$hard_weight_threshold` | 硬性权重阈值 | 3 |
| `$min_criteria` / `$max_criteria` | 输出条数区间 | 2 / 6 |

**② 发送请求。** system 用渲染结果；user 按 `prompts/criteria.user.md` 填 `$query`（画像原文）与
`$conditions_block`（用户手写补充条件，每行一条 `- 条件`，没有则为空）。建议参数：
`temperature=0`、JSON 输出格式、`max_tokens` ≥ 4096（上限是防截断，不是目标）。

**③ 校验输出。** 模型只返回 `{"criteria": [...]}`；接入方必须做**白名单校验**后再入库：

- `category` ∈ 契约枚举；`weight` 为 1–5 整数；`name` ≤ 22 汉字；`question` 以问号结尾
- `expected` 按该维 `expected_kind` 校验：`text` 非空 / `enum` 落在契约枚举内（seniority 必须是
  「决策层/管理层/执行层/一线」之一，判定器要拿它去职级阶梯里查位置）/ `empty` 恰为 `""`
- `tokens` 非空（seniority 除外——它的取值在 expected 里）；`lenient` 与契约声明一致；
  每维条数 ≤ `max`；总条数在区间内
- 不合规条目逐条剔除；**通过数 < 2 时整批弃用**——半份标准比没有更危险

## 输出契约（单条标准）

```json
{"category": "seniority", "name": "职级：管理层", "weight": 3,
 "question": "候选人的职级是否达到管理层？",
 "tokens": ["总监", "head of", "director", "CMO"],
 "expected": "管理层", "lenient": false, "note": "门槛取画像出现的最低档"}
```

| 字段 | 约束 |
| --- | --- |
| `category` | 必须是契约枚举之一 |
| `name` | 人类可读，「维度：取值」，≤ 22 个汉字 |
| `question` | 判定口径，一句话，以问号结尾 |
| `weight` | 整数 1–5；达到阈值为**硬性标准**，判「不符合」则结论不得为「明确符合」 |
| `tokens` | 用于**子串匹配**的短关键词数组（职称语言不定，中英文写法都给），不要写句子 |
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
4. **枚举里每个维度都必须能被现有数据判定**——人物判定的数据源是公开职业档案，规模与融资
   在档案上不存在，**永远不要**把它们加回维度枚举。
5. **`reachability` 不让模型产出**——与画像内容无关，任何画像都适用，由接入方统一补。
6. **姓名宁可不认，不可认错**——只在画像明确点名（引号、称呼、「名叫/姓名是」等提示词）时输出
   name 标准；姓名是权重 5 的硬性标准，猜错的代价是整批候选被判「不符合」。

## 已知教训（实测换来的）

- `seniority.expected` 必须落在阶梯枚举内：写成「总监及以上」这类人类说法，下游无法与档案职级比较。
- 档案上的职称语言不确定：中文画像也要在 tokens 里给英文写法（「市场」→ ["市场","marketing","CMO"]），
  只存中文会在英文档案上整批漏判。
- `temperature=0` 不等于可复现：同一句输入连跑三次标准名就会变——比结构，不要比文案。
- 用户手写条件的「并入」逻辑会与 LLM 打架：接入方做条件合并时，引擎自己下发过的条件名回传回来
  要能识别并跳过，否则权重表翻倍、结论漂移。
