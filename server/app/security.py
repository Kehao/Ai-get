"""无状态令牌：载荷用 HMAC-SHA256 签名，服务无需保存会话表。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from .config import SECRET_KEY, TOKEN_TTL_SECONDS

_ALGORITHM = "sha256"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload: bytes) -> str:
    digest = hmac.new(SECRET_KEY.encode(), payload, _ALGORITHM).digest()
    return _b64encode(digest)


def create_token(email: str, issued_at: float | None = None) -> str:
    """为指定邮箱签发令牌，载荷包含主题与过期时间。"""
    issued = time.time() if issued_at is None else issued_at
    payload = json.dumps({"sub": email, "exp": issued + TOKEN_TTL_SECONDS}).encode()
    return f"{_b64encode(payload)}.{_sign(payload)}"


def read_token(token: str) -> str | None:
    """校验令牌并返回邮箱；非法或过期时返回 None。"""
    parts = token.split(".")
    if len(parts) != 2:
        return None

    payload_text, signature = parts
    try:
        payload = _b64decode(payload_text)
    except (ValueError, base64.binascii.Error):
        return None

    if not hmac.compare_digest(_sign(payload), signature):
        return None

    claims = json.loads(payload)
    if claims.get("exp", 0) < time.time():
        return None

    subject = claims.get("sub")
    return subject if isinstance(subject, str) else None
