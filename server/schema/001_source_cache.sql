-- 001_source_cache.sql
-- 数据源结果缓存：providers/cache.py 的 SQLite 存储介质（P7 替换进程内字典）。
--
-- 语义与进程内版本严格一致：
--   * value 为 pickle 序列化的任意缓存对象（CompanyRecord / PDL profile / 百度
--     references 等，本地代码自己写入，无反序列化不可信数据的场景）；
--   * 「源确认过没有这条数据」由调用方的值语义承载（各源缓存空串哨兵），
--     缓存层不区分 miss 与空结果；
--   * 过期行不主动删（读时判断 expires_at），写满触发兜底清理，避免写放大。

CREATE TABLE IF NOT EXISTS source_cache (
    cache_key  TEXT PRIMARY KEY,            -- 完整缓存键，如 "tavily:search:...:25"、"baidu:webenrich:{dedupe_key}"
    source_id  TEXT NOT NULL,               -- 键首段（产生结果的源 id：tavily / baidu / pdl），便于按源清理与审计
    value      BLOB NOT NULL,               -- pickle 序列化的缓存对象
    created_at INTEGER NOT NULL,            -- 写入时间，Unix 秒
    expires_at INTEGER NOT NULL             -- 过期时间，Unix 秒（写入时 = created_at + TTL）
);

-- 读路径：按 key 取值并检查过期。索引即主键，无需额外索引。
-- 写路径：INSERT OR REPLACE（同一 key 重新计时）。

-- 兜底清理：删除已过期超过 7 天的行（过期后仍短暂保留，便于排查「为什么重新扣费」）。
-- 应用层可用 "DELETE FROM source_cache WHERE expires_at < strftime('%s','now') - 604800;" 定期执行。
