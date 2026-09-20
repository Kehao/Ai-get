-- 005_mining_rows.sql
-- 每次挖掘的候选行：一条召回记录 + 它的判定结果。「这份名单为什么长这样」的事实存档。
--
-- record_json 存完整 CompanyRecord / PersonRecord（两类结构不同，**不合并列**，
-- 与「不合并行类型」的项目约定一致，靠 mining_lists.mode 区分）；
-- judgment_json 存 CriterionVerdict 列表 + score + verdict。
-- 独立出 score/verdict 列：按命中状态筛选候选是高频操作，不解析 JSON。

CREATE TABLE IF NOT EXISTS mining_rows (
    row_id       TEXT PRIMARY KEY,          -- 行 id（现有 rows 的 uuid hex）
    list_id      TEXT NOT NULL,             -- 所属挖掘列表（mining_lists.id）
    dedupe_key   TEXT NOT NULL DEFAULT '',  -- 企业去重键；people 行为空串（person 无 dedupe 语义）
    record_json  TEXT NOT NULL,             -- 完整召回记录 JSON（含 evidence / attributes / missing_fields）
    judgment_json TEXT NOT NULL DEFAULT '[]',  -- 判定结果 JSON（逐条 CriterionVerdict + score）
    score        REAL NOT NULL DEFAULT 0,   -- 综合得分（排序用，冗余自 judgment）
    verdict      TEXT NOT NULL DEFAULT 'unknown',  -- 'qualified' | 'partial' | 'unqualified' | 'unknown'
    created_at   INTEGER NOT NULL,          -- Unix 秒
    FOREIGN KEY (list_id) REFERENCES mining_lists (id) ON DELETE CASCADE
);

-- 列表详情页：按得分倒序取行（与前端展示排序一致）。
CREATE INDEX IF NOT EXISTS idx_mining_rows_list_score
    ON mining_rows (list_id, score DESC);

-- 跨列表查同一企业的所有历史判定（复购/回访场景）：
CREATE INDEX IF NOT EXISTS idx_mining_rows_dedupe
    ON mining_rows (dedupe_key) WHERE dedupe_key != '';

-- 候选去重的核心查询（P6 路线图原话「重复挖掘要能命中」）：
--   已见过的企业 = SELECT DISTINCT dedupe_key FROM mining_rows WHERE dedupe_key = ?;
-- 或在召回时直接查 companies 表的 last_seen_at。
