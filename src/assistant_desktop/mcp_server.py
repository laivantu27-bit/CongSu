from __future__ import annotations

import sys

from assistant_desktop.browser_tools import read_webpage
from assistant_desktop.desktop_tools import DesktopToolError
from assistant_desktop.memory import MemoryStore
from assistant_desktop.workspace_tools import (
    delete_workspace_file,
    get_workspace_root,
    list_workspace,
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
        """Ghi tệp tối đa 1 MB trong workspace; cấu hình MCP client để hỏi trước."""
        return write_workspace_file(root, path, content)

    @server.tool()
    def workspace_delete(path: str) -> str:
        """Xóa một tệp duy nhất trong workspace; cấu hình MCP client để hỏi trước."""
        return delete_workspace_file(root, path)

    @server.tool()
    def webpage_read(url: str) -> str:
        """Đọc trang web công khai qua Playwright, không click hay gửi biểu mẫu."""
        return read_webpage(url)

    @server.tool()
    def allowed_command(command_id: str) -> str:
        """Chạy một lệnh phiên bản cố định; không nhận lệnh shell tùy ý."""
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
        """Lưu một ghi chú memory không nhạy cảm theo yêu cầu."""
        memory.add(fact)
        return "Đã lưu ghi chú memory cục bộ."

    @server.tool()
    def memory_clear() -> str:
        """Xóa toàn bộ memory cục bộ."""
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
