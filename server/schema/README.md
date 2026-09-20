# SQLite Schema（P7 持久化）

P7 的目标：**候选缓存与去重跨会话生效**——真实数据源按次计费，进程重启后缓存必须还在，
同一企业重复挖掘不能重复扣费。本目录是建表 DDL 的真源，每个文件一张表，
全部使用 `CREATE TABLE IF NOT EXISTS` 保证幂等执行。

## 文件清单

| 文件 | 表 | 职责 |
| --- | --- | --- |
| `001_source_cache.sql` | `source_cache` | 数据源结果缓存（替换 `providers/cache.py` 的进程内字典） |
| `002_companies.sql` | `companies` | 企业主档：跨挖掘的去重主键（dedupe_key） |
| `003_company_enrichments.sql` | `company_enrichments` | 补齐台账：哪个字段、哪个源、什么时候给的 |
| `004_mining_lists.sql` | `mining_lists` | 挖掘列表主档（替换 `_ListState` 的内存单例） |
| `005_mining_rows.sql` | `mining_rows` | 每次挖掘的候选行（记录 + 判定结果） |

## 设计约定

1. **时间一律 `INTEGER`**，Unix 秒（`strftime('%s','now')`），方便 TTL 直接比较与算术。
2. **JSON 一律 `TEXT`** 存序列化字符串；SQLite 3.38+ 有 JSON1 函数可按需查询，
   但应用层不做 JSON 内部索引——需要查询的维度都提升成独立列。
3. **`dedupe_key`** 与 `CompanyRecord.dedupe_key` 同口径：域名小写优先，缺失退化到名称小写。
   它是 `companies` / `company_enrichments` / `mining_rows` 之间的事实外键（不设物理外键约束，
   由应用层保证——缓存表允许先于主档存在）。
4. **空串哨兵语义贯通**：`source_cache.value = ''` 表示「源确认过没有这条数据」，
   与「从未缓存」严格区分，和进程内版本的行为完全一致。
5. **连接 pragma**（应用层执行）：`journal_mode=WAL`（读写不互斥）、
   `foreign_keys=ON`、`busy_timeout=5000`。
6. **不做的**：用户/账号体系、评分与判定历史的全量版本化——当前产品是单用户内存语义，
   这些等有真实需求再加，避免设计出没人用的表。

## 迁移方式

P7 实现时按文件名序号依次执行（简单的 `PRAGMA user_version` 记录已应用到的最大序号即可），
不引入 Alembic 这类重迁移框架。
