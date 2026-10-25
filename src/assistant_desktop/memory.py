from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_FACT_PATTERNS = (
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

    def remember_user_message(self, message: str) -> list[str]:
        if _SENSITIVE_CONTENT.search(message):
            return []

        saved: list[str] = []
        with self._connect() as connection:
            for category, pattern in _FACT_PATTERNS:
                for match in pattern.finditer(message):
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

    def clear(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories")
            return cursor.rowcount

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
