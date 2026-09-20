-- 004_mining_lists.sql
-- 挖掘列表主档：对应 repositories/targets.py 的 _ListState / TargetList，
-- P7 后重启进程不再丢失历史列表，刷新页面后仍可回看。
--
-- criteria / columns / condition_items / strategy_groups / follow_up_plan
-- 都是「列表级配置或展示态」——数量小、只随列表整体读写，故作 JSON 列而不拆表；
-- 需要独立查询的候选行拆到 005_mining_rows。

CREATE TABLE IF NOT EXISTS mining_lists (
    id               TEXT PRIMARY KEY,      -- list_id（uuid hex 12 位，与现有 API 路由一致）
    query            TEXT NOT NULL,         -- 用户画像原文
    mode             TEXT NOT NULL,         -- 'company' | 'people'（CHECK 兜底防脏数据）
    status           TEXT NOT NULL,         -- 'running' | 'completed' | 'failed'（沿用现有状态机词汇）
    progress         INTEGER NOT NULL DEFAULT 0,
    requested_count  INTEGER NOT NULL,      -- 用户要的候选数量
    discovered_count INTEGER NOT NULL DEFAULT 0,
    contact_count    INTEGER NOT NULL DEFAULT 0,
    seed             INTEGER NOT NULL DEFAULT 0,  -- 召回随机种子：同 seed 可复现同一次召回
    condition_items_json  TEXT NOT NULL DEFAULT '[]',   -- 用户确认过的条件项
    strategy_groups_json  TEXT NOT NULL DEFAULT '[]',   -- 策略分组文案
    criteria_json         TEXT NOT NULL DEFAULT '[]',   -- L0 生成的加权标准
    columns_json          TEXT NOT NULL DEFAULT '[]',   -- 动态列定义
    follow_up_plan_json   TEXT,                          -- 跟进计划（可能为 NULL）
    recall_source_id TEXT NOT NULL DEFAULT '',    -- 召回来源源 id（"mock" / "tavily" / "mock+..."）
    created_at       INTEGER NOT NULL,      -- Unix 秒
    updated_at       INTEGER NOT NULL,      -- 最近一次状态变更，Unix 秒
    CHECK (mode IN ('company', 'people')),
    CHECK (status IN ('running', 'completed', 'failed'))
);

-- 列表页按时间倒序展示：
CREATE INDEX IF NOT EXISTS idx_mining_lists_created
    ON mining_lists (created_at DESC);
