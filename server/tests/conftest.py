"""pytest 全局配置：在任何测试模块 import app 之前生效。

源缓存默认写 `server/data/source_cache.db`（真实持久化），测试必须隔离——
在 conftest 顶层设环境变量，让 config 在被 import 时就拿到 :memory: 路径。
"""

import os

os.environ.setdefault("AIGET_SOURCE_CACHE_DB", ":memory:")
