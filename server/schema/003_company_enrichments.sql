-- 003_company_enrichments.sql
-- 补齐台账：一家企业被哪个源补过什么字段、什么时候补的。「字段可信度」的事实依据。
--
-- 设计取舍：每个 (dedupe_key, source_id) 只保留**最新一份**（UPSERT 覆盖），
-- 不做逐次历史版本化——补齐是幂等动作，重放没有业务价值；需要审计时源端有账单。
-- 字段值整体序列化在 payload JSON 里（CompanyRecord 形状），抽出的照面字段
-- 同时落在 fields_json 便于直接阅读，不拆列——字段集会随源演化，拆列是维护负担。

CREATE TABLE IF NOT EXISTS company_enrichments (
    dedupe_key  TEXT NOT NULL,              -- 企业去重键（对应 companies.dedupe_key）
    source_id   TEXT NOT NULL,              -- 补齐源 id（baidu / pdl / tavily）
    fields_json TEXT NOT NULL,              -- 可读的字段快照：{"summary": "...", "registered_capital": "...", ...}
    payload     TEXT NOT NULL,              -- 完整 CompanyRecord JSON（含 evidence、attributes、matched_title）
    fetched_at  INTEGER NOT NULL,           -- 本次补齐时间，Unix 秒
    PRIMARY KEY (dedupe_key, source_id)
);

-- 「这家企业都被谁补过什么」：主键即覆盖。
-- 「这个源最近补了多少家」（配额审计）：
CREATE INDEX IF NOT EXISTS idx_enrichments_source_time
    ON company_enrichments (source_id, fetched_at);

-- 读路径（合并字段时）：
--   SELECT source_id, payload FROM company_enrichments WHERE dedupe_key = ? ORDER BY fetched_at;
-- 应用层按源的 priority（pd(20) > baidu(30) > tavily(40)）决定合并顺序。
