from __future__ import annotations

import sys

from assistant_desktop.browser_tools import (
    automate_webpage,
    describe_browser_session_tool,
    execute_browser_session_tool,
    read_webpage,
)
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
        from mcp.types import ToolAnnotations
    except ImportError as error:
        raise RuntimeError(
            'Thiếu MCP SDK. Cài đặt bằng: py -m pip install -e ".[mcp]"'
        ) from error

    server = FastMCP("congsu-assistant")
    root = get_workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore()

    def run_browser_tool(name: str, arguments: dict[str, object]) -> str:
        if name not in {
            "list_browser_tabs",
            "read_page",
            "wait_for_load",
        } and not mcp_permission_enabled("browser_automation"):
            raise DesktopToolError(
                "MCP browser automation đang tắt. Bật "
                "ASSISTANT_MCP_ALLOW_BROWSER_AUTOMATION sau khi cấu hình "
                "xác nhận cho từng thao tác."
            )
        describe_browser_session_tool(name, arguments)
        return execute_browser_session_tool(name, arguments)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def workspace_list(path: str = ".") -> list[dict[str, str]]:
        """Liệt kê tệp trong workspace được giới hạn."""
        return list_workspace(root, path)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def workspace_read(path: str) -> str:
        """Đọc một tệp UTF-8 trong workspace."""
        return read_workspace_file(root, path)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def workspace_search(
        query: str, path: str = "."
    ) -> list[dict[str, str | int]]:
        """Tìm chuỗi trong tệp UTF-8 của workspace."""
        from assistant_desktop.workspace_tools import search_workspace

        return search_workspace(root, query, path)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def workspace_mkdir(path: str) -> str:
        """Tạo thư mục; yêu cầu ASSISTANT_MCP_ALLOW_FILE_WRITE bật."""
        if not mcp_permission_enabled("file_write"):
            raise DesktopToolError("MCP file write đang tắt.")
        from assistant_desktop.workspace_tools import create_workspace_directory

        return create_workspace_directory(root, path)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def workspace_copy(source: str, destination: str) -> str:
        """Sao chép tệp; yêu cầu ASSISTANT_MCP_ALLOW_FILE_WRITE bật."""
        if not mcp_permission_enabled("file_write"):
            raise DesktopToolError("MCP file write đang tắt.")
        from assistant_desktop.workspace_tools import copy_workspace_file

        return copy_workspace_file(root, source, destination)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def workspace_move(source: str, destination: str) -> str:
        """Di chuyển tệp; yêu cầu ASSISTANT_MCP_ALLOW_FILE_WRITE bật."""
        if not mcp_permission_enabled("file_write"):
            raise DesktopToolError("MCP file write đang tắt.")
        from assistant_desktop.workspace_tools import move_workspace_file

        return move_workspace_file(root, source, destination)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def workspace_write(path: str, content: str) -> str:
        """Ghi tệp trong workspace; yêu cầu ASSISTANT_MCP_ALLOW_FILE_WRITE bật."""
        if not mcp_permission_enabled("file_write"):
            raise DesktopToolError(
                "MCP file write đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_FILE_WRITE "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        return write_workspace_file(root, path, content)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def workspace_delete(path: str) -> str:
        """Xóa một tệp; yêu cầu ASSISTANT_MCP_ALLOW_FILE_DELETE bật."""
        if not mcp_permission_enabled("file_delete"):
            raise DesktopToolError(
                "MCP file delete đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_FILE_DELETE "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        return delete_workspace_file(root, path)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def webpage_read(url: str) -> str:
        """Đọc trang web công khai qua Playwright, không click hay gửi biểu mẫu."""
        return read_webpage(url)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
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

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def open_browser(url: str) -> str:
        """Mở trang công khai trong phiên nhiều tab; yêu cầu quyền browser automation."""
        return run_browser_tool("open_browser", {"url": url})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def list_browser_tabs() -> str:
        """Liệt kê các tab Playwright đang mở."""
        return run_browser_tool("list_browser_tabs", {})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def read_page(tab_id: str) -> str:
        """Đọc nội dung tab cùng cảnh báo login/CAPTCHA."""
        return run_browser_tool("read_page", {"tab_id": tab_id})

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def navigate_browser(tab_id: str, url: str) -> str:
        """Điều hướng tab tới URL công khai; yêu cầu quyền browser automation."""
        return run_browser_tool(
            "navigate_browser", {"tab_id": tab_id, "url": url}
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def click_by_text(tab_id: str, text: str) -> str:
        """Click nội dung chính xác, không gửi form; yêu cầu quyền browser automation."""
        return run_browser_tool(
            "click_by_text", {"tab_id": tab_id, "text": text}
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def click_selector(tab_id: str, selector: str) -> str:
        """Click CSS selector, không gửi form; yêu cầu quyền browser automation."""
        return run_browser_tool(
            "click_selector", {"tab_id": tab_id, "selector": selector}
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def fill_form(tab_id: str, label: str, value: str) -> str:
        """Điền trường không nhạy cảm; không hỗ trợ login hoặc gửi form."""
        return run_browser_tool(
            "fill_form",
            {"tab_id": tab_id, "label": label, "value": value},
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def scroll_page(tab_id: str, direction: str, amount: int) -> str:
        """Cuộn trang tối đa 2.000 pixel; yêu cầu quyền browser automation."""
        return run_browser_tool(
            "scroll_page",
            {"tab_id": tab_id, "direction": direction, "amount": amount},
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def wait_for_load(
        tab_id: str, state: str, timeout_ms: int = 15000
    ) -> str:
        """Chờ trang tải với timeout tối đa 15 giây."""
        return run_browser_tool(
            "wait_for_load",
            {"tab_id": tab_id, "state": state, "timeout_ms": timeout_ms},
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    def close_browser_tab(tab_id: str) -> str:
        """Đóng tab Playwright; yêu cầu quyền browser automation."""
        return run_browser_tool("close_browser_tab", {"tab_id": tab_id})

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def allowed_command(command_id: str) -> str:
        """Chạy tác vụ allowlist; yêu cầu ASSISTANT_MCP_ALLOW_SYSTEM_COMMANDS bật."""
        if not mcp_permission_enabled("system_commands"):
            raise DesktopToolError(
                "MCP system commands đang tắt. Bật "
                "ASSISTANT_MCP_ALLOW_SYSTEM_COMMANDS trong tiến trình MCP tin cậy."
            )
        return run_allowed_command(command_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def memory_search(query: str) -> list[str]:
        """Tìm ghi chú memory cục bộ liên quan."""
        return memory.recall(query)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def memory_list() -> list[str]:
        """Liệt kê memory cục bộ."""
        return memory.list_memories()

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def memory_add(fact: str) -> str:
        """Lưu ghi chú; yêu cầu ASSISTANT_MCP_ALLOW_MEMORY_WRITE bật."""
        if not mcp_permission_enabled("memory_write"):
            raise DesktopToolError(
                "MCP memory write đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_MEMORY_WRITE "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        memory.add(fact)
        return "Đã lưu ghi chú memory cục bộ."

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def memory_delete(fact: str) -> str:
        """Xóa một ghi chú cụ thể; yêu cầu ASSISTANT_MCP_ALLOW_MEMORY_DELETE bật."""
        if not mcp_permission_enabled("memory_delete"):
            raise DesktopToolError(
                "MCP memory delete đang tắt. Bật ASSISTANT_MCP_ALLOW_MEMORY_DELETE "
                "trong tiến trình MCP tin cậy."
            )
        if not memory.delete(fact):
            raise DesktopToolError("Không tìm thấy ghi chú memory khớp chính xác.")
        return "Đã xóa ghi chú memory."

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    def memory_clear() -> str:
        """Xóa memory; yêu cầu ASSISTANT_MCP_ALLOW_MEMORY_CLEAR bật."""
        if not mcp_permission_enabled("memory_clear"):
            raise DesktopToolError(
                "MCP memory clear đang tắt. Chỉ bật ASSISTANT_MCP_ALLOW_MEMORY_CLEAR "
                "trong tiến trình MCP tin cậy sau khi cấu hình xác nhận phía client."
            )
        return f"Đã xóa {memory.clear()} ghi chú memory."

    @server.resource(
        "assistant://capabilities",
        name="Assistant capabilities",
        description="Tool và giới hạn an toàn của CongSu Assistant.",
        mime_type="text/markdown",
    )
    def capabilities_resource() -> str:
        return (
            "# CongSu Assistant tools\n"
            "- Workspace: list/read/search; mkdir/copy/move/write/delete trong workspace.\n"
            "- Browser: 10-tab Playwright session; public HTTP(S), chỉ GET/HEAD; "
            "đọc, điều hướng, click text/CSS, điền trường an toàn, cuộn, chờ tải.\n"
            "- Browser không gửi form, không đăng nhập hoặc giải CAPTCHA; "
            "automation cần bật quyền và xác nhận.\n"
            "- Memory: search/list; write/delete/clear cần quyền riêng.\n"
            "- Commands: version, tests, compile và Git status allowlist; không có shell tùy ý.\n"
            "- Quyền ghi/xóa file, memory, browser automation, system commands bị khóa mặc định.\n"
            "- Thao tác nhạy cảm cần xác nhận ở MCP client trước khi bật từng quyền.\n"
        )

    @server.prompt(
        name="safe_assistant",
        title="Safe CongSu Assistant",
        description="Hướng dẫn client dùng tool với quyền tối thiểu và xác nhận.",
    )
    def safe_assistant_prompt() -> str:
        return (
            "Dùng tool đúng theo yêu cầu người dùng. Đọc trước khi sửa; trình bày "
            "đường dẫn, nội dung và tác động cụ thể trước thao tác thay đổi. "
            "Không thử lệnh shell tùy ý, không vượt workspace, không gửi biểu mẫu "
            "web hoặc dữ liệu nhạy cảm. Dùng tab_id được trả về cho browser; "
            "không đăng nhập, không xử lý CAPTCHA và không click nút submit. "
            "Yêu cầu client xác nhận mọi thao tác "
            "ghi/xóa, browser automation và lệnh hệ thống."
        )

    return server


def main() -> None:
    try:
        create_server().run(transport="stdio")
    except (DesktopToolError, OSError, RuntimeError, ValueError) as error:
        print(f"MCP server error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
