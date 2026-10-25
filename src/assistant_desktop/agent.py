from __future__ import annotations

from threading import Event
from typing import Any

from PySide6.QtCore import QThread, Signal

from assistant_desktop.desktop_tools import (
    DesktopToolError,
    describe_tool_call,
    execute_tool,
    get_tool_definitions,
)
from assistant_desktop.ollama import OllamaClient, OllamaError

MAX_TOOL_CALLS_PER_TURN = 5


class ToolApprovalRequest:
    def __init__(self, description: str) -> None:
        self.description = description
        self._approved = False
        self._resolved = Event()

    def resolve(self, approved: bool) -> None:
        self._approved = approved
        self._resolved.set()

    def wait(self, timeout: float = 300.0) -> bool | None:
        if not self._resolved.wait(timeout):
            return None
        return self._approved


class AgentWorker(QThread):
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    approval_requested = Signal(object)

    def __init__(
        self,
        client: OllamaClient,
        messages: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self._client = client
        self._messages = messages
        self._tool_definitions = get_tool_definitions()
        self._tool_calls = 0

    def run(self) -> None:
        try:
            response = self._run_agent()
        except OllamaError as error:
            self.failed.emit(str(error), self._messages)
            return
        self.succeeded.emit(response, self._messages)

    def _run_agent(self) -> str:
        for _ in range(MAX_TOOL_CALLS_PER_TURN + 1):
            message = self._client.chat_message(
                self._messages,
                tools=self._tool_definitions,
            )
            tool_calls = message.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                raise OllamaError("Ollama trả về danh sách tool-call không hợp lệ.")
            if not tool_calls:
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise OllamaError(
                        "Ollama không trả về câu trả lời hoặc tool-call hợp lệ."
                    )
                self._messages.append(
                    {"role": "assistant", "content": content.strip()}
                )
                return content.strip()

            parsed_calls = self._parse_tool_calls(tool_calls)
            if parsed_calls is None:
                error_message = (
                    "Mô hình đề xuất một thao tác có định dạng không hợp lệ; "
                    "không có thao tác nào được thực hiện."
                )
                self._messages.append(
                    {"role": "assistant", "content": error_message}
                )
                return error_message

            if self._tool_calls + len(parsed_calls) > MAX_TOOL_CALLS_PER_TURN:
                return self._finish(
                    "Mình đã dừng vì yêu cầu vượt quá giới hạn "
                    f"{MAX_TOOL_CALLS_PER_TURN} thao tác trong một lượt."
                )

            assistant_content = message.get("content", "")
            if not isinstance(assistant_content, str):
                return self._finish(
                    "Mô hình trả về nội dung tool-call không hợp lệ; "
                    "không có thao tác nào được thực hiện."
                )
            self._messages.append(message)
            for index, (name, arguments) in enumerate(parsed_calls):
                self._tool_calls += 1
                tool_result = self._run_tool(name, arguments)
                self._messages.append(tool_result)
                if tool_result["content"].startswith(
                    ("Người dùng đã từ chối", "Không nhận được xác nhận")
                ):
                    for remaining_name, _ in parsed_calls[index + 1 :]:
                        self._messages.append(
                            {
                                "role": "tool",
                                "tool_name": remaining_name,
                                "content": (
                                    "Không thực hiện vì thao tác trước đó "
                                    "không được xác nhận."
                                ),
                            }
                        )
                    return self._finish(
                        "Mình đã dừng thao tác vì không có xác nhận."
                    )

        return self._finish(
            "Mình đã dừng sau khi đạt giới hạn thao tác cho một lượt."
        )

    def _run_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, str]:
        try:
            description = describe_tool_call(name, arguments)
        except DesktopToolError as error:
            return {
                "role": "tool",
                "tool_name": name,
                "content": f"Thao tác không được chấp nhận: {error}",
            }

        approval = ToolApprovalRequest(description)
        self.approval_requested.emit(approval)
        decision = approval.wait()
        if decision is not True:
            content = (
                "Người dùng đã từ chối thao tác; không được thử lại."
                if decision is False
                else "Không nhận được xác nhận; thao tác không được thực hiện."
            )
            return {
                "role": "tool",
                "tool_name": name,
                "content": content,
            }

        try:
            result = execute_tool(name, arguments)
        except (
            DesktopToolError,
            ImportError,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            result = f"Thao tác thất bại: {error}"
        return {"role": "tool", "tool_name": name, "content": result}

    @staticmethod
    def _parse_tool_calls(
        tool_calls: list[Any],
    ) -> list[tuple[str, dict[str, Any]]] | None:
        parsed: list[tuple[str, dict[str, Any]]] = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                return None
            function = tool_call.get("function")
            if not isinstance(function, dict):
                return None
            name = function.get("name")
            arguments = function.get("arguments")
            if not isinstance(name, str) or not name:
                return None
            if not isinstance(arguments, dict):
                return None
            parsed.append((name, arguments))
        return parsed

    def _finish(self, response: str) -> str:
        self._messages.append({"role": "assistant", "content": response})
        return response
