from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when Ollama cannot complete a chat request."""


def create_chat_payload(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    return payload


class OllamaClient:
    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        timeout: float = 120.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    def chat_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request = Request(
            f"{self._host}/api/chat",
            data=json.dumps(
                create_chat_payload(self._model, messages, tools),
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            raise OllamaError(
                f"Ollama trả về HTTP {error.code}: {detail or error.reason}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise OllamaError(
                "Không kết nối được Ollama. Hãy kiểm tra Ollama đang chạy "
                f"tại {self._host} và thử lại. Chi tiết: {error}"
            ) from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise OllamaError("Ollama trả về dữ liệu không hợp lệ.") from error

        if not isinstance(result, dict):
            raise OllamaError("Ollama trả về dữ liệu không đúng định dạng.")
        message = result.get("message")
        if not isinstance(message, dict):
            raise OllamaError("Ollama không trả về message hợp lệ.")
        return message

    def chat(self, messages: list[dict[str, Any]]) -> str:
        message = self.chat_message(messages)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama không trả về nội dung câu trả lời.")
        return content.strip()
