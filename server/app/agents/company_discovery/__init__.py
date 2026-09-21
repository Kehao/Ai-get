"""实体发现 agent：检索网页 → 提炼实体 → 逐级深挖补全。

- 入口：`run_discovery_agent`（全流程）、`discover_entities`（只出候选）、
  `deepen_entity`（单家深挖）——三者同时从包根 `app.agents` 导出；
- 配置：`configs/<name>.json`（字段表 + 预算）；
- 提示词：`prompts/*.md`；
- 项目适配（百度 / DeepSeek / 抓取的协议实现）：`adapters.py`。
"""
