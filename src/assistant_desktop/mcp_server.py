from __future__ import annotations

import sys

from assistant_desktop.browser_tools import read_webpage
from assistant_desktop.browser_tools import automate_webpage
from assistant_desktop.desktop_tools import DesktopToolError, describe_tool_call
from assistant_desktop.memory import MemoryStore
from assistant_desktop.workspace_tools import (
    delete_workspace_file,
    get_workspace_root,
    list_workspace,
    mcp_permission_enabled,
    read_workspace_file,
    run_allowed_command,
    write_workspace_file,
)


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            'Thiếu MCP SDK. Cài đặt bằng: py -m pip install -e ".[mcp]"'
        ) from error

    server = FastMCP("congsu-assistant")
    root = get_workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore()

    @server.tool()
    def workspace_list(path: str = ".") -> list[dict[str, str]]:
        """Liệt kê tệp trong workspace được giới hạn."""
        return list_workspace(root, path)

    @server.tool()
    def workspace_read(path: str) -> str:
        """Đọc một tệp UTF-8 trong workspace."""
        return read_workspace_file(root, path)

    @server.tool()
    def workspace_write(path: str, content: str) -> str:
        """Ghi tệp trong workspace; yêu cầu ASSISTANT_MCP_ALLOW_FILE_WRITE bật."""
        if not mcp_permission_enabled("file_write"):
            raise DesktopToolError(
                "MCP file write đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_FILE_WRITE "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        return write_workspace_file(root, path, content)

    @server.tool()
    def workspace_delete(path: str) -> str:
        """Xóa một tệp; yêu cầu ASSISTANT_MCP_ALLOW_FILE_DELETE bật."""
        if not mcp_permission_enabled("file_delete"):
            raise DesktopToolError(
                "MCP file delete đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_FILE_DELETE "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        return delete_workspace_file(root, path)

    @server.tool()
    def webpage_read(url: str) -> str:
        """Đọc trang web công khai qua Playwright, không click hay gửi biểu mẫu."""
        return read_webpage(url)

    @server.tool()
    def webpage_automate(
        url: str, actions: list[dict[str, str]]
    ) -> str:
        """Tự động hóa browser; yêu cầu ASSISTANT_MCP_ALLOW_BROWSER_AUTOMATION bật."""
        if not mcp_permission_enabled("browser_automation"):
            raise DesktopToolError(
                "MCP browser automation đang tắt. Bật "
                "ASSISTANT_MCP_ALLOW_BROWSER_AUTOMATION trong tiến trình MCP "
                "tin cậy sau khi cấu hình xác nhận phía client."
            )
        describe_tool_call(
            "browser_automate", {"url": url, "actions": actions}
        )
        return automate_webpage(url, actions)

    @server.tool()
    def allowed_command(command_id: str) -> str:
        """Chạy lệnh phiên bản cố định; yêu cầu ASSISTANT_MCP_ALLOW_SYSTEM_COMMANDS bật."""
        if not mcp_permission_enabled("system_commands"):
            raise DesktopToolError(
                "MCP system commands đang tắt. Bật "
                "ASSISTANT_MCP_ALLOW_SYSTEM_COMMANDS trong tiến trình MCP tin cậy."
            )
        return run_allowed_command(command_id)

    @server.tool()
    def memory_search(query: str) -> list[str]:
        """Tìm ghi chú memory cục bộ liên quan."""
        return memory.recall(query)

    @server.tool()
    def memory_list() -> list[str]:
        """Liệt kê memory cục bộ."""
        return memory.list_memories()

    @server.tool()
    def memory_add(fact: str) -> str:
        """Lưu ghi chú; yêu cầu ASSISTANT_MCP_ALLOW_MEMORY_WRITE bật."""
        if not mcp_permission_enabled("memory_write"):
            raise DesktopToolError(
                "MCP memory write đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_MEMORY_WRITE "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        memory.add(fact)
        return "Đã lưu ghi chú memory cục bộ."

    @server.tool()
    def memory_clear() -> str:
        """Xóa memory; yêu cầu ASSISTANT_MCP_ALLOW_MEMORY_CLEAR bật."""
        if not mcp_permission_enabled("memory_clear"):
            raise DesktopToolError(
                "MCP memory clear đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_MEMORY_CLEAR "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        return f"Đã xóa {memory.clear()} ghi chú memory."

    return server


def main() -> None:
    try:
        create_server().run(transport="stdio")
    except (DesktopToolError, OSError, RuntimeError, ValueError) as error:
        print(f"MCP server error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
