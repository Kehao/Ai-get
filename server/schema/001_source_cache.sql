-- 001_source_cache.sql
-- 数据源结果缓存：providers/cache.py 的 SQLite 存储介质（P7 替换进程内字典）。
--
-- 语义与进程内版本严格一致：
--   * value = ''   → 空串哨兵，表示「源确认过没有这条数据」，命中后不再重复扣费探测；
--   * value = JSON → 序列化的缓存对象（CompanyRecord / PDL profile / 百度 references 等）；
--   * 过期行不删（读时判断 expires_at），由定期清理语句兜底删除，避免写放大。

CREATE TABLE IF NOT EXISTS source_cache (
    cache_key  TEXT PRIMARY KEY,            -- 完整缓存键，如 "tavily:search:...:25"、"baidu:webenrich:{dedupe_key}"
    source_id  TEXT NOT NULL,               -- 产生该结果的源 id（tavily / baidu / pdl），便于按源清理与审计
    value      TEXT NOT NULL,               -- JSON 序列化的缓存对象；'' = 确认为空的哨兵
    created_at INTEGER NOT NULL,            -- 写入时间，Unix 秒
    expires_at INTEGER NOT NULL             -- 过期时间，Unix 秒（写入时 = created_at + TTL）
);

-- 读路径：按 key 取值并检查过期。索引即主键，无需额外索引。
-- 写路径：INSERT OR REPLACE（同一 key 重新计时）。

-- 兜底清理：删除已过期超过 7 天的行（过期后仍短暂保留，便于排查「为什么重新扣费」）。
-- 应用层可用 "DELETE FROM source_cache WHERE expires_at < strftime('%s','now') - 604800;" 定期执行。
