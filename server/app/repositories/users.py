"""用户仓库。

演示环境不接数据库：账号以常量形式内置，登录后签发无状态令牌。
"""

from __future__ import annotations

import threading
import uuid

from ..models import User

DEMO_EMAIL = "qiukehao388@126.com"
DEMO_PASSWORD = "m831027"


class UserRepository:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._passwords: dict[str, str] = {}
        self._lock = threading.RLock()
        self._seed_demo_user()

    def _seed_demo_user(self) -> None:
        self._store(DEMO_EMAIL, DEMO_PASSWORD, display_name="qiukehao388")

    def _store(self, email: str, password: str, display_name: str) -> User:
        user = User(
            id=f"user-{uuid.uuid4().hex[:8]}",
            email=email,
            display_name=display_name,
        )
        self._users[email] = user
        self._passwords[email] = password
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        with self._lock:
            stored_password = self._passwords.get(email)
            if stored_password is None or stored_password != password:
                return None
            return self._users[email]

    def register(self, email: str, password: str) -> User | None:
        """创建账号。邮箱已存在时返回 None，由调用方转成 409。"""
        with self._lock:
            if email in self._users:
                return None
            return self._store(email, password, display_name=email.split("@")[0])

    def find(self, email: str) -> User | None:
        with self._lock:
            return self._users.get(email)
