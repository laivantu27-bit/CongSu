from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from assistant_desktop.desktop_tools import DesktopToolError

DEFAULT_WORKSPACE_ROOT = Path(r"C:\CongSu\workspace")
MAX_FILE_BYTES = 1_000_000
ALLOWED_COMMANDS: dict[str, tuple[str, ...]] = {
    "python_version": ("python", "--version"),
    "git_version": ("git", "--version"),
    "ollama_version": ("ollama", "--version"),
}

WORKSPACE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "workspace_list",
            "description": "Liệt kê tệp và thư mục trong workspace được cho phép.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read",
            "description": "Đọc tệp văn bản trong workspace được cho phép.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_write",
            "description": "Tạo hoặc ghi đè tệp văn bản trong workspace được cho phép.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "maxLength": MAX_FILE_BYTES},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_delete",
            "description": "Xóa một tệp duy nhất bên trong workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_allowed_command",
            "description": (
                "Chạy một lệnh chỉ-đọc cố định để xem phiên bản Python, Git "
                "hoặc Ollama. Không nhận lệnh hay đối số tùy ý."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command_id": {
                        "type": "string",
                        "enum": list(ALLOWED_COMMANDS),
                    }
                },
                "required": ["command_id"],
                "additionalProperties": False,
            },
        },
    },
]


def resolve_workspace_path(
    root: str | Path, relative_path: str, *, allow_root: bool = False
) -> Path:
    if not isinstance(relative_path, str) or "\x00" in relative_path:
        raise DesktopToolError("Đường dẫn workspace không hợp lệ.")
    workspace = Path(root).resolve()
    candidate_input = Path(relative_path)
    if candidate_input.is_absolute():
        candidate = candidate_input.resolve()
    else:
        candidate = (workspace / candidate_input).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as error:
        raise DesktopToolError("Đường dẫn nằm ngoài workspace được cho phép.") from error
    if candidate == workspace and not allow_root:
        raise DesktopToolError("Thao tác này cần đường dẫn tệp cụ thể.")
    return candidate


def get_workspace_root() -> Path:
    configured = os.environ.get("ASSISTANT_WORKSPACE")
    return Path(configured) if configured else DEFAULT_WORKSPACE_ROOT


def list_workspace(root: str | Path, relative_path: str = ".") -> list[dict[str, str]]:
    directory = resolve_workspace_path(root, relative_path, allow_root=True)
    if not directory.is_dir():
        raise DesktopToolError("Đường dẫn workspace không phải thư mục.")
    return [
        {
            "name": item.name,
            "type": "directory" if item.is_dir() else "file",
        }
        for item in sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    ]


def read_workspace_file(root: str | Path, relative_path: str) -> str:
    file_path = resolve_workspace_path(root, relative_path)
    if not file_path.is_file():
        raise DesktopToolError("Tệp không tồn tại hoặc không phải tệp thường.")
    if file_path.stat().st_size > MAX_FILE_BYTES:
        raise DesktopToolError("Tệp vượt quá giới hạn đọc 1 MB.")
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise DesktopToolError("Chỉ hỗ trợ đọc tệp văn bản UTF-8.") from error


def write_workspace_file(
    root: str | Path, relative_path: str, content: str
) -> str:
    file_path = resolve_workspace_path(root, relative_path)
    if not isinstance(content, str):
        raise DesktopToolError("Nội dung tệp phải là văn bản.")
    try:
        content_size = len(content.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise DesktopToolError("Nội dung phải là văn bản UTF-8 hợp lệ.") from error
    if content_size > MAX_FILE_BYTES:
        raise DesktopToolError("Tệp vượt quá giới hạn ghi 1 MB.")
    if not file_path.parent.is_dir():
        raise DesktopToolError("Thư mục đích không tồn tại trong workspace.")
    if file_path.exists() and not file_path.is_file():
        raise DesktopToolError("Chỉ hỗ trợ ghi tệp thường.")
    try:
        file_path.write_text(content, encoding="utf-8", newline="")
    except OSError as error:
        raise DesktopToolError(f"Không thể ghi tệp: {error}") from error
    return f"Đã ghi tệp workspace: {file_path.name}."


def delete_workspace_file(root: str | Path, relative_path: str) -> str:
    file_path = resolve_workspace_path(root, relative_path)
    if not file_path.is_file():
        raise DesktopToolError("Chỉ có thể xóa một tệp thường đã tồn tại.")
    try:
        file_path.unlink()
    except OSError as error:
        raise DesktopToolError(f"Không thể xóa tệp: {error}") from error
    return f"Đã xóa tệp workspace: {file_path.name}."


def run_allowed_command(command_id: str) -> str:
    command = ALLOWED_COMMANDS.get(command_id)
    if command is None:
        raise DesktopToolError("Lệnh không nằm trong danh sách cho phép.")
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DesktopToolError(f"Không thể chạy lệnh phiên bản: {error}") from error
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        raise DesktopToolError(
            f"Lệnh kết thúc với mã {result.returncode}: {output[:500]}"
        )
    return output[:500] or "Lệnh hoàn tất nhưng không có đầu ra."


def validate_workspace_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DesktopToolError("Tham số tool phải là object.")
    allowed = {
        "workspace_list": (set(), {"path"}),
        "workspace_read": ({"path"}, set()),
        "workspace_write": ({"path", "content"}, set()),
        "workspace_delete": ({"path"}, set()),
        "run_allowed_command": ({"command_id"}, set()),
    }.get(name)
    if allowed is None:
        raise DesktopToolError(f"Tool không được phép: {name}")
    required, optional = allowed
    keys = set(arguments)
    if not required <= keys or keys - required - optional:
        raise DesktopToolError("Tham số tool thiếu hoặc có trường không được phép.")
    if name == "workspace_list" and not keys:
        return {"path": "."}
    for field in required:
        if not isinstance(arguments[field], str):
            raise DesktopToolError(f"Tham số {field} phải là chuỗi.")
    if name == "workspace_write":
        content = arguments["content"]
        if not isinstance(content, str):
            raise DesktopToolError("Nội dung tệp phải là văn bản.")
        try:
            content_size = len(content.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise DesktopToolError("Nội dung phải là văn bản UTF-8 hợp lệ.") from error
        if content_size > MAX_FILE_BYTES:
            raise DesktopToolError("Tệp vượt quá giới hạn ghi 1 MB.")
    return arguments.copy()


def describe_workspace_tool(name: str, arguments: dict[str, Any]) -> str:
    validated = validate_workspace_tool(name, arguments)
    if name == "workspace_write":
        content = validated["content"]
        return (
            f"Ghi tệp workspace: {validated['path']}\n"
            f"Kích thước: {len(content.encode('utf-8'))} byte\n"
            "Nội dung chính xác sẽ được hiển thị trong hộp thoại xác nhận:\n\n"
            + content
        )
    if name == "workspace_delete":
        return f"Xóa tệp {validated['path']} trong workspace."
    if name == "run_allowed_command":
        return (
            f"Chạy lệnh cố định {validated['command_id']}: "
            + " ".join(ALLOWED_COMMANDS[validated["command_id"]])
        )
    if name == "workspace_read":
        return f"Đọc tệp {validated['path']} trong workspace."
    return f"Liệt kê thư mục {validated['path']} trong workspace."


def execute_workspace_tool(
    name: str,
    arguments: dict[str, Any],
    root: str | Path,
) -> str:
    validated = validate_workspace_tool(name, arguments)
    if name == "workspace_list":
        return "\n".join(
            f"{item['type']}: {item['name']}"
            for item in list_workspace(root, validated["path"])
        ) or "(thư mục trống)"
    if name == "workspace_read":
        return read_workspace_file(root, validated["path"])
    if name == "workspace_write":
        return write_workspace_file(root, validated["path"], validated["content"])
    if name == "workspace_delete":
        return delete_workspace_file(root, validated["path"])
    if name == "run_allowed_command":
        return run_allowed_command(validated["command_id"])
    raise DesktopToolError(f"Tool không được phép: {name}")


def mcp_permission_enabled(permission: str) -> bool:
    env_var = {
        "file_write": "ASSISTANT_MCP_ALLOW_FILE_WRITE",
        "file_delete": "ASSISTANT_MCP_ALLOW_FILE_DELETE",
        "memory_write": "ASSISTANT_MCP_ALLOW_MEMORY_WRITE",
        "memory_clear": "ASSISTANT_MCP_ALLOW_MEMORY_CLEAR",
        "browser_automation": "ASSISTANT_MCP_ALLOW_BROWSER_AUTOMATION",
        "system_commands": "ASSISTANT_MCP_ALLOW_SYSTEM_COMMANDS",
    }.get(permission)
    if env_var is None:
        raise DesktopToolError("Quyền MCP không hợp lệ.")
    return os.environ.get(env_var, "").casefold() in {"1", "true", "yes"}
