---
name: python
description: Python 编码规范与最佳实践。在编写、审查或重构 Python 代码时使用，覆盖 PEP 8 风格、提交前检查、版本要求、依赖管理、Pythonic 写法、反模式、测试与 docstring。由 AGENTS.md 引用。
---

# Python 编码规范

## 代码风格（PEP 8）

- 缩进使用 4 个空格（绝不用 Tab）。
- 每行最长 88 字符（Black 默认）或 79 字符（严格 PEP 8）。
- 顶层定义之间空两行，类内部方法之间空一行。
- 导入顺序：标准库 → 第三方 → 本地模块，组内按字母序排列。
- 函数与变量用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_CASE`。

## 提交前检查

按顺序执行，任一步失败必须先修好再提交：

```bash
# 1. 语法检查（始终执行）
python -m py_compile $(git ls-files '*.py')

# 2. 测试（优先 pytest，不可用时回退 unittest）
if python -m pytest --version >/dev/null 2>&1; then
    python -m pytest -q
else
    python -m unittest discover -q
fi

# 3. 静态检查与格式（工具已安装时执行）
if command -v ruff >/dev/null 2>&1; then
    ruff check . --fix && ruff format .
elif command -v black >/dev/null 2>&1; then
    python -m black --check .
fi
```

## Python 版本

- **最低要求：** Python 3.10+（3.9 已于 2025 年 10 月停止维护）。
- **推荐目标：** 新项目使用 Python 3.11 — 3.13。
- 绝不使用 Python 2 的语法或写法。
- 使用现代特性：`match` 语句、海象运算符、类型注解。

## 依赖管理

优先使用 uv，其次回退到 pip；两者都只装在虚拟环境内，不要污染系统环境。

```bash
if command -v uv >/dev/null 2>&1; then
    uv pip install <package>
    uv pip compile requirements.in -o requirements.txt
else
    pip install <package>
fi
```

- 使用 uv 创建新项目：`uv init`，或 `uv venv && source .venv/bin/activate`。
- 锁定并提交依赖版本（`uv.lock` 或 `requirements.txt`）。

## Pythonic 写法

```python
# ✅ 用列表/字典推导式替代循环
squares = [x**2 for x in range(10)]
lookup = {item.id: item for item in items}

# ✅ 用上下文管理器管理资源
with open("file.txt") as f:
    data = f.read()

# ✅ 解包
first, *rest = items
a, b = b, a  # 交换变量

# ✅ 先尝试后捕获（EAFP）优于先检查后执行（LBYL）
try:
    value = d[key]
except KeyError:
    value = default

# ✅ 用 f-string 做格式化
msg = f"Hello {name}, you have {count} items"

# ✅ 类型注解
def process(items: list[str]) -> dict[str, int]:
    ...

# ✅ 用 dataclasses/attrs 定义数据容器
from dataclasses import dataclass

@dataclass
class User:
    name: str
    email: str
    active: bool = True

# ✅ 用 pathlib 替代 os.path
from pathlib import Path
config = Path.home() / ".config" / "app.json"

# ✅ 善用 enumerate、zip、itertools
for i, item in enumerate(items):
    ...
for a, b in zip(list1, list2, strict=True):
    ...
```

## 需要避免的反模式

```python
# ❌ 可变的默认参数：所有调用共享同一个列表
def bad(items=[]):
    ...

# ✅ 改为 None 哨兵
def good(items=None):
    items = items or []

# ❌ 裸 except：会连 SystemExit、KeyboardInterrupt 一起捕获
try:
    ...
except:
    ...

# ✅ 指明异常类型
try:
    ...
except Exception:
    ...
```

- ❌ 全局可变状态。
- ❌ 通配符导入（`from module import *`）。
- ❌ 循环内拼接字符串（应使用 `join`）。
- ❌ `== None`（应使用 `is None`）。
- ❌ `len(x) == 0`（应使用 `not x`）。

## 测试

- 使用 pytest（首选）或 unittest。
- 测试文件命名为 `test_*.py`，测试函数命名为 `test_*`。
- 聚焦小型单元测试，mock 掉外部依赖。
- 每次提交前运行：`python -m pytest -v`。

## Docstring 文档字符串

```python
def fetch_user(user_id: int, include_deleted: bool = False) -> User | None:
    """Fetch a user by ID from the database.
    （按 ID 从数据库获取用户）

    Args:
        user_id: The unique user identifier.（用户的唯一标识）
        include_deleted: If True, include soft-deleted users.
            （若为 True，则包含软删除的用户）

    Returns:
        User object if found, None otherwise.
        （找到则返回 User 对象，否则返回 None）

    Raises:
        DatabaseError: If connection fails.（若连接失败则抛出）
    """
```

> 注：上述 docstring 示例保持 Google 风格的中英文对照写法。推荐实际编码时用英文写 docstring（便于协作与工具解析），中文说明作为补充。

## 快速检查清单

- [ ] 语法有效（`py_compile`）。
- [ ] 测试通过（`pytest`）。
- [ ] 公开函数带类型注解。
- [ ] 无硬编码密钥。
- [ ] 使用 f-string，而非 `.format()` 或 `%`。
- [ ] 文件路径使用 `pathlib`。
- [ ] I/O 使用上下文管理器。
- [ ] 无可变默认参数。
- [ ] 依赖安装在虚拟环境内，锁文件已更新。
