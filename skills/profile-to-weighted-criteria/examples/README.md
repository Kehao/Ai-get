# 典型实例

每份样例只有三样东西：**输入**（`profile` / `user_conditions`）、**输出**（`criteria`）、
**一句话看点**（`_note`）。`valid/` 是真实 LLM 调用快照，`invalid/` 是反面样本。

```json
{
  "_note": "一句话看点",
  "profile": "输入的画像",
  "user_conditions": [],
  "criteria": [ … 每行一条标准 … ]
}
```

`criteria` 之外都是说明性元数据，**校验器只读 `criteria`**，所以样例本身就是可直接运行的校验输入。

## 正面样例：输入 → 最重要的输出

格式：`维度` 取值 **权重**（标「宽松」的即 `lenient: true`）。

| 输入（画像） | 输出 | tokens |
| --- | --- | --- |
| 杭州的消费品与旅游行业小微商家，员工 50 人以下，最好近期有融资或中标动态 | `geo`杭州 **5** · `industry`消费品与旅游 **5** · `size` `0:50` **3** · `signal`近期融资 **2**宽松 · `signal`近期中标 **2**宽松 | 1776 |
| 深圳的跨境电商物流服务商 | `geo`深圳 **5** · `industry`跨境电商物流 **5** · `business`跨境物流服务能力 **3**宽松 · `business`服务电商卖家 **2**宽松 | 1667 |
| 上海的生物医药 CRO 企业，已完成 B 轮融资 | `geo`上海 **5** · `industry`生物医药CRO **5** · `funding`**`B轮`** **3** | 1707 |
| 北京的 SaaS 企业服务公司<br>+「必须是一年内新成立的公司」「不接受人力外包型公司」 | `geo`北京 **5** · `industry`企业服务与软件 **5** · `business`成立一年内 **3**宽松 · `business`非人力外包 **3**宽松 | 2413 |
| 成都的环保科技企业，有过 A 轮融资，且近 6 个月内获得过政府补贴 | `geo`成都 **5** · `industry`环保科技 **5** · `funding`**`A轮`** **3** · `business`近6个月政府补贴 **3**宽松 | 1552 |

五份各有一个看点：

| 文件 | 看点 |
| --- | --- |
| `01-hangzhou-consumer-tourism` | 最标准的形状：四个维度写全，硬性 5/5/3 + 宽松 2 |
| `02-shenzhen-crossborder-logistics` | 画像只说两件事 → 只输出两维，**没有**编造 `size` / `funding` |
| `03-shanghai-biotech-cro` | `funding` 走枚举：`expected` 逐字落在 `"B轮"`，不是「B 轮」 |
| `04-beijing-saas-user-conditions` | 用户条件被完整纳入，**但代码后处理有 3 个缺陷**（见下） |
| `05-chengdu-greentech-timewindow` | 「近 6 个月」没有维度承载，只能降级成宽松项 |

### 04 号值得单独看

文件带 `_issues`。三个缺陷**都不是模型的错**，换更强的模型也不会好：

1. **极性反转** —— 用户写「**不接受**人力外包型公司」，而代码的行业族词表里含「外包」二字，
   于是这条件被当成该行业族命中，把用户要**排除**的词并进了**正向**行业标准。
   结果：一家人力外包公司反而**符合** w=5 的硬性行业标准。
2. **整句当 token** —— 未被规则识别的条件兜底成 `tokens: ["必须是一年内新成立的公司"]`，
   永远不可能命中，是纯噪音；而校验器**拦不住**（12 字 < 30 字上限，格式完全合法）。
3. **契约无否定语义** —— 没有字段表达「不符合则排除」，模型只能把否定条件写成正向
   `question`（命中即「符合」），真实含义只能塞进 `note`，**而判定器不读 `note`**。

完整分析见 `references/pitfalls.md` 第 11 条。

## 反面样本：一份只触发一条规则

| 文件 | 触发的规则 |
| --- | --- |
| `01-size-expected-is-natural-language` | `size.expected` 写成「50 人以下」，下游 `int()` 会崩 |
| `02-weight-is-string` | `weight` 是字符串 `"5"`（`bool` 是 `int` 子类，判类型必须显式排除） |
| `03-business-lenient-must-be-true` | 宽松项给了 `false`，会让冷门行业集体掉档 |
| `04-geo-lenient-must-be-false` | 硬性骨架给了 `true`，等于放水 |
| `05-category-out-of-enum` | 越界输出 `reachability`（由代码统一补，不让模型自作主张） |
| `06-per-category-over-limit` | `geo` 输出两条，超过该维度上限 |
| `07-question-without-question-mark` | `question` 不以问号结尾 |
| `08-size-tokens-must-be-empty` | `size.tokens` 非空（规模用结构化 `expected` 表达） |
| `09-funding-expected-not-in-enum` | `funding.expected` 写成 `"D轮"`，不在枚举里 |
| `10-too-few-criteria` | 只有 1 条，低于下限 2（半份标准比没有更危险） |
| `11-too-many-criteria` | 9 条，超过上限 8 |
| `12-name-too-long` | `name` 超过 22 字 |

## 一条命令自查两组退出码

```bash
cd skills/profile-to-weighted-criteria
for f in examples/valid/*.json;   do python3 scripts/validate_criteria.py "$f" >/dev/null || echo "✗ 应通过却失败：$f"; done
for f in examples/invalid/*.json; do python3 scripts/validate_criteria.py "$f" >/dev/null && echo "✗ 应拒绝却漏过：$f"; done
```

## 两点注意

- **不要拿样例做字面回归。** 模型非确定性：同一句画像连跑三次标准名就会变
  （见 `references/pitfalls.md` 第 3 条）。要比结构（维度集合、条数区间、`expected_kind`），不要比文案。
- **样例里没有 `reachability`。** 它由代码在模型输出之后统一补（见 `contract.json` 的
  `excluded_categories`），不属于模型的职责；拿补完的列表去校验一定报越界，那不是 bug。

抓取信息：2026-09-20，模型 `deepseek-flash`，契约 `criteria/v1`，五份样例各 1 次外部请求。

## 移植示例

`porting/` 演示把维度枚举从 B2B 换成招聘：六个维度其实是**同一组形状**（`text` / `range` /
`enum` / `empty`）换了名字与词表。它同时说明为什么「只换一个文件」不够——规则引擎那边还有
三张表要对齐，而一致性守卫会在**加载那一秒**把差异报出来。
