from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

_FACT_PATTERNS = (
    (
        "explicit",
        re.compile(
            r"\b(?:hãy nhớ|nhớ giúp tôi|nhớ giúp mình|ghi nhớ)\s+"
            r"(?:rằng\s+)?([^.!?\r\n]{2,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "preference",
        re.compile(
            r"\b(?:tôi|mình)\s+(?:thích|yêu thích|ưa thích|quan tâm đến)\s+"
            r"([^.!?\r\n]{2,200})",
            re.IGNORECASE,
        ),
    ),
    (
        "activity",
        re.compile(
            r"\b(?:tôi|mình)\s+(?:đang học|đang làm|làm việc với)\s+"
            r"([^.!?\r\n]{2,200})",
            re.IGNORECASE,
        ),
    ),
)
_SENSITIVE_CONTENT = re.compile(
    r"\b(?:mật khẩu|password|passcode|mã otp|one.time password|"
    r"api.?key|access.?token|secret|số thẻ|cvv)\b|"
    r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|"
    r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)",
    re.IGNORECASE,
)


class MemoryStore:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            app_data = Path(
                os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")
            )
            path = app_data / "CongSu" / "memory.sqlite3"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    fact TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS conversation_messages_by_time
                ON conversation_messages(conversation_id, id)
                """
            )

    def create_conversation(self, title: str = "Cuộc trò chuyện mới") -> str:
        conversation_id = uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'),
                           strftime('%Y-%m-%d %H:%M:%f', 'now'))
                """,
                (conversation_id, title[:100]),
            )
        return conversation_id

    def save_conversation_message(
        self, conversation_id: str, role: str, content: str
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Chỉ lưu được tin nhắn user hoặc assistant.")
        if len(content) > 100_000:
            raise ValueError("Tin nhắn vượt quá giới hạn lưu 100.000 ký tự.")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO conversation_messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (conversation_id, role, content),
            )
            if role == "user":
                title = " ".join(content.split())[:100] or "Cuộc trò chuyện mới"
                connection.execute(
                    """
                    UPDATE conversations
                    SET title = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
                    WHERE id = ? AND NOT EXISTS (
                        SELECT 1 FROM conversation_messages
                        WHERE conversation_id = ? AND id < ?
                    )
                    """,
                    (title, conversation_id, conversation_id, cursor.lastrowid),
                )
            else:
                connection.execute(
                    """
                    UPDATE conversations
                    SET updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
                    WHERE id = ?
                    """,
                    (conversation_id,),
                )

    def list_conversations(self, limit: int = 50) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, updated_at FROM conversations
                ORDER BY updated_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {"id": row[0], "title": row[1], "updated_at": row[2]}
            for row in rows
        ]

    def load_conversation(
        self, conversation_id: str, limit: int | None = None
    ) -> list[dict[str, str]]:
        if limit is None:
            query = """
                SELECT role, content FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY id
            """
            parameters: tuple[str | int, ...] = (conversation_id,)
        else:
            query = """
                SELECT role, content FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY id DESC LIMIT ?
            """
            parameters = (conversation_id, limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        if limit is not None:
            rows.reverse()
        return [{"role": role, "content": content} for role, content in rows]

    def clear_conversations(self) -> int:
        with self._connect() as connection:
            connection.execute("DELETE FROM conversation_messages")
            cursor = connection.execute("DELETE FROM conversations")
            return cursor.rowcount

    def remember_user_message(self, message: str) -> list[str]:
        if _SENSITIVE_CONTENT.search(message):
            return []

        saved: list[str] = []
        matched_facts = [
            (category, match)
            for category, pattern in _FACT_PATTERNS
            for match in pattern.finditer(message)
        ]
        if any(category == "explicit" for category, _ in matched_facts):
            matched_facts = [
                (category, match)
                for category, match in matched_facts
                if category == "explicit"
            ]
        with self._connect() as connection:
            for category, match in matched_facts:
                detail = " ".join(match.group(1).split()).strip()
                if len(detail) < 2:
                    continue
                fact = f"{category}: {detail}"
                connection.execute(
                    """
                    INSERT INTO memories (category, fact)
                    VALUES (?, ?)
                    ON CONFLICT(fact) DO UPDATE SET
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (category, fact),
                )
                saved.append(fact)
        return saved

    def add(self, fact: str) -> None:
        normalized = " ".join(fact.split()).strip()
        if not normalized or len(normalized) > 500:
            raise ValueError("Memory phải có từ 1 đến 500 ký tự.")
        if _SENSITIVE_CONTENT.search(normalized):
            raise ValueError("Không lưu thông tin nhạy cảm trong memory.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (category, fact)
                VALUES ('manual', ?)
                ON CONFLICT(fact) DO UPDATE SET created_at = CURRENT_TIMESTAMP
                """,
                (f"manual: {normalized}",),
            )

    def recall(self, query: str, limit: int = 5) -> list[str]:
        terms = {
            term.casefold()
            for term in re.findall(r"[^\W_]{2,}", query, flags=re.UNICODE)
        }
        if not terms:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT fact FROM memories ORDER BY created_at DESC, id DESC"
            ).fetchall()
        ranked = []
        for (fact,) in rows:
            fact_terms = {
                term.casefold()
                for term in re.findall(r"[^\W_]{2,}", fact, flags=re.UNICODE)
            }
            score = len(terms & fact_terms)
            if score:
                ranked.append((score, fact))
        if not ranked and re.search(
            r"\b(?:nhớ|memory|ghi chú|biết về tôi|biết về mình)\b",
            query,
            flags=re.IGNORECASE,
        ):
            return [fact for (fact,) in rows[: min(limit, 3)]]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [fact for _, fact in ranked[:limit]]

    def list_memories(self, limit: int = 50) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT fact FROM memories ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [fact for (fact,) in rows]

    def delete(self, fact: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE fact = ?",
                (fact,),
            )
            return cursor.rowcount > 0

    def clear(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories")
            return cursor.rowcount

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()
