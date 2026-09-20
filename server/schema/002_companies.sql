-- 002_companies.sql
-- 企业主档：跨挖掘会话的去重主键。同一家公司无论被哪个源、哪次挖掘召回，
-- 在这里只有一行——「重复挖掘不重复出现、不重复扣费」的事实依据。
--
-- dedupe_key 与 CompanyRecord.dedupe_key 同口径：域名小写优先，缺失退化到名称小写。
-- 画像字段（summary/industries 等）不在这里冗余：它们属于补齐结果，查 003_company_enrichments。

CREATE TABLE IF NOT EXISTS companies (
    dedupe_key   TEXT PRIMARY KEY,          -- 去重键：域名小写（优先）或名称小写
    name         TEXT NOT NULL,             -- 最新一次见到的名称（会被更新）
    domain       TEXT NOT NULL DEFAULT '',  -- 官网域名，缺域名的候选为空串
    first_seen_source TEXT NOT NULL,        -- 首次发现的源 id（tavily / mock / …）
    first_seen_at     INTEGER NOT NULL,     -- 首次发现时间，Unix 秒
    last_seen_at      INTEGER NOT NULL,     -- 最近一次出现在任何挖掘结果中的时间，Unix 秒
    seen_count        INTEGER NOT NULL DEFAULT 1  -- 累计被召回次数：热度的粗粒度信号
);

-- 「这次挖掘的候选是否已经见过」是最频繁的查询：按 key 主键直查即可。
-- 按源统计首次发现分布（如「本周真实源召回多少家」）：
CREATE INDEX IF NOT EXISTS idx_companies_first_seen_source
    ON companies (first_seen_source, first_seen_at);

-- 写路径：INSERT ... ON CONFLICT(dedupe_key) DO UPDATE
--   SET name=excluded.name, last_seen_at=excluded.last_seen_at, seen_count=seen_count+1;
