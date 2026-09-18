"""知识库仓库。新建知识库时按来源生成问答集，供智能体训练使用。"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from ..models import (
    CreateKnowledgeBaseRequest,
    KnowledgeBase,
    KnowledgeBaseDetail,
    KnowledgeEntry,
)
from ..mock.catalog import KNOWLEDGE_QA_TEMPLATES


class KnowledgeRepository:
    def __init__(self) -> None:
        self._bases: dict[str, KnowledgeBase] = {}
        self._entries: dict[str, list[KnowledgeEntry]] = {}
        self._lock = threading.RLock()

    def all(self) -> list[KnowledgeBase]:
        with self._lock:
            return sorted(self._bases.values(), key=lambda item: item.created_at, reverse=True)

    def create(self, request: CreateKnowledgeBaseRequest) -> KnowledgeBaseDetail:
        knowledge_base_id = uuid.uuid4().hex[:12]
        entries = _build_entries(knowledge_base_id, request.name, request.source_url)
        knowledge_base = KnowledgeBase(
            id=knowledge_base_id,
            name=request.name,
            source_url=request.source_url,
            status="completed",
            entry_count=len(entries),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._bases[knowledge_base_id] = knowledge_base
            self._entries[knowledge_base_id] = entries
        return KnowledgeBaseDetail(knowledge_base=knowledge_base, entries=entries)

    def detail(self, knowledge_base_id: str) -> KnowledgeBaseDetail | None:
        with self._lock:
            knowledge_base = self._bases.get(knowledge_base_id)
            if knowledge_base is None:
                return None
            return KnowledgeBaseDetail(
                knowledge_base=knowledge_base,
                entries=list(self._entries[knowledge_base_id]),
            )

    def delete(self, knowledge_base_id: str) -> bool:
        with self._lock:
            self._entries.pop(knowledge_base_id, None)
            return self._bases.pop(knowledge_base_id, None) is not None


def _build_entries(knowledge_base_id: str, name: str, source_url: str) -> list[KnowledgeEntry]:
    """按模板生成问答，并在首条注入知识库名称，使内容与来源相关。"""
    entries: list[KnowledgeEntry] = []
    for index, template in enumerate(KNOWLEDGE_QA_TEMPLATES):
        question = template.question if index > 0 else f"{name}主要提供什么？"
        answer = template.answer if index > 0 else f"{name}的知识库来自 {source_url or '手动录入素材'}，{template.answer}"
        entries.append(
            KnowledgeEntry(
                id=f"{knowledge_base_id}-qa-{index}",
                question=question,
                answer=answer,
            )
        )
    return entries
