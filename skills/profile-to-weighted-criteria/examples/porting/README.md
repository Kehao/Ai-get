# 移植示例：把「潜客挖掘」换成「招聘筛选」

本目录只有一个文件 `recruiting-contract.json`，它的作用是**把「领域无关」这句话变成可检查的东西**：
把 B2B 的维度枚举换成招聘的，看看到底要动哪些地方、哪些地方**不能**动。

> ⚠️ **它不是可以直接替换的配置。** 直接把它当 `contract.json` 用会被一致性守卫拦下——
> 见下面「为什么不只是换个文件」。

## 一、维度怎么对应

| B2B 潜客挖掘 | 招聘筛选 | `expected_kind` | 为什么 |
| --- | --- | --- | --- |
| `geo` 地域 | `city` 城市 | `text` | 都是「一个可枚举的地名」，形态相同，只是换了名字 |
| `industry` 行业 | `function` 职能 | `text` | 都是「一句业务/岗位归类」，靠关键词子串匹配 |
| `size` 规模 | `experience` 年限 | `range` | 都是**数值区间**：`"0:50"`（人）↔ `"3:5"`（年）。形态完全一致 |
| `funding` 融资阶段 | `education` 学历 | `enum` | 都是「有限的阶梯」：未融资/天使/A/B/C ↔ 不限/大专/本科/硕士/博士 |
| `business` 业务特征 | `skill` 技能 | `empty` | 都是「宽松的多条特征」，靠 `tokens` 匹配、查不到不判不符合 |
| `signal` 动作线索 | `signal` 求职信号 | `empty` | 都是「正在发生的动作」：融资/中标 ↔ 在职看机会/可到岗 |
| ~~`reachability`~~ | ~~`contactability`~~ | — | **都排除在外**，由代码统一补：能不能联系上与被筛选对象无关，任何画像都适用 |

**关键观察：六个维度是同一组「形状」，只是换了名字与词表。**
这就是这个技能能跨领域的原因——`expected_kind` 的四型（`text` / `range` / `enum` / `empty`）覆盖了
「可机器判定的取值形态」，而具体是什么领域只影响 `name` 与 `tokens_hint`。

## 二、为什么不只是换个文件

改完 `contract.json` 还不够，**规则引擎那边还有三张表**（Ai-get 在
`server/app/qualification/criteria.py`）：

| 表 | 作用 | 不改会怎样 |
| --- | --- | --- |
| `_LLM_CATEGORIES` | 白名单：模型输出的 `category` 必须 ∈ 它 | 模型按新维度输出，判定器全部拒绝 |
| `_MAX_PER_CATEGORY` | 每维度条数上限 | 条数上限形同虚设 |
| `CATEGORY_WEIGHTS` | 默认权重与硬性阈值 | 权重按 B2B 的骨架给，与招聘场景不符 |

这些**有意不放进** `contract.json`：它们是规则引擎自己的表，让技能目录另存一份就等于制造第二个真源。

加载时会**逐项断言**两边一致，不一致直接抛错。实测把本目录的契约指给加载器：

```
$ AIGET_LLM_PROMPT_DIR=<repo>/examples/porting python -c "from app.llm import load_asset; load_asset()"
PromptAssetError: /…/examples/porting/contract.json 的维度枚举与
criteria._LLM_CATEGORIES 不一致：相差
['business','city','education','experience','function','funding','geo','industry','size','skill']
```

> 报错里「相差」列的是**两个集合的对称差**，所以 B2B 的旧维度（business/funding/geo/industry/size）
> 与招聘的新维度（city/education/experience/function/skill）会一起列出来。看这个列表就知道还差哪些没对齐。

**这不是失败，是这个机制最大的价值**：它把「改了契约表却忘了改引擎」这种漂移，
从「运行一段时间后表现为全批降级」提前到了「加载那一秒报错并指出差了哪几个」。

## 三、换成真的能跑，需要做的完整步骤

1. 改 `contract.json` 的 `categories`（照抄本文件的结构）+ `version` bump 成 `recruiting-v1`；
2. 改规则引擎的 `_LLM_CATEGORIES` / `_MAX_PER_CATEGORY` / `CATEGORY_WEIGHTS` 三张表；
3. 改 `prompts/criteria.system.md` 里**领域相关的措辞**（占位符不用动，契约表会自动渲染）：
   - 「B2B 销售线索挖掘系统的『资格标准引擎』」→ 招聘场景的说法；
   - 「真实可能出现在中文**工商信息或企业官网**里的词」→ 招聘场景里应当是**简历与招聘平台**的措辞；
   - 硬性规则第 6 条举的例子是「近 6 个月完成融资」→ 换成招聘里的时间窗（如「近 3 个月在职」）；
4. 改 `prompts/criteria.user.md` 里的「客户画像：」→「候选人要求：」；
5. 改 `scripts/validate_criteria.py`？**不用**——它读 `contract.json`，自动跟随；
6. 改 `references/prompt.md` 的快照（重新渲染一次即可）。

第 5 步是这个重构最直接的收益：**旧版校验器的契约常量写在脚本顶部，移植时必须人肉同步，
漏了就会出现「模型按新枚举输出、校验器按旧枚举拒绝」的假故障。**
