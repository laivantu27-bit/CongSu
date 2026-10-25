from __future__ import annotations

import os
import time
import webbrowser
from typing import Any
from urllib.parse import urlsplit

MAX_TYPED_CHARACTERS = 500
AUTO_APPROVED_TOOLS = frozenset(
    {
        "click",
        "type_text",
        "press_key",
        "read_webpage",
        "workspace_list",
        "workspace_read",
    }
)
APPLICATIONS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "paint": "mspaint.exe",
}
KEYS = {
    "enter": "enter",
    "tab": "tab",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "page_up": "pageup",
    "page_down": "pagedown",
}


class DesktopToolError(RuntimeError):
    """Raised when a desktop tool request is invalid or cannot be performed."""


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": (
                "Mở Notepad, Calculator, File Explorer, Paint hoặc trình duyệt "
                "mặc định. Chỉ dùng khi người dùng yêu cầu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_id": {
                        "type": "string",
                        "enum": [
                            "notepad",
                            "calculator",
                            "explorer",
                            "paint",
                            "browser",
                        ],
                    },
                    "url": {
                        "type": "string",
                        "description": "URL http/https tùy chọn, chỉ dùng với browser.",
                    },
                },
                "required": ["app_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click chuột trái hoặc phải tại tọa độ màn hình.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "minimum": 0},
                    "y": {"type": "integer", "minimum": 0},
                    "button": {"type": "string", "enum": ["left", "right"]},
                },
                "required": ["x", "y"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": (
                "Gõ tối đa 500 ký tự vào cửa sổ đang hoạt động. Có thể dùng "
                "clipboard Windows tạm thời để hỗ trợ tiếng Việt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_TYPED_CHARACTERS,
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Nhấn một phím điều hướng hoặc phím nhập đã cho phép.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": list(KEYS),
                    }
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": (
                "Đọc nội dung văn bản từ trang web công khai http/https bằng "
                "Playwright. Chỉ đọc; không click, gửi biểu mẫu hoặc đăng nhập."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "maxLength": 2048},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_automate",
            "description": (
                "Mở trang công khai rồi click theo nội dung chính xác, điền "
                "trường theo nhãn hoặc nhấn phím cho phép. Tối đa 8 hành động; "
                "mọi lần gọi cần người dùng xác nhận. Không đăng nhập hoặc tải tệp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "maxLength": 2048},
                    "actions": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "click_text",
                                        "click_role",
                                        "fill_label",
                                        "select_label",
                                        "check_label",
                                        "uncheck_label",
                                        "press_key",
                                    ],
                                },
                                "text": {"type": "string", "maxLength": 500},
                                "label": {"type": "string", "maxLength": 500},
                                "value": {"type": "string", "maxLength": 500},
                                "role": {
                                    "type": "string",
                                    "enum": ["button", "link"],
                                },
                                "name": {"type": "string", "maxLength": 500},
                                "key": {
                                    "type": "string",
                                    "enum": [
                                        "Tab",
                                        "Escape",
                                        "Backspace",
                                        "Delete",
                                        "ArrowUp",
                                        "ArrowDown",
                                        "ArrowLeft",
                                        "ArrowRight",
                                    ],
                                },
                            },
                            "required": ["type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["url", "actions"],
                "additionalProperties": False,
            },
        },
    },
]


def get_tool_definitions() -> list[dict[str, Any]]:
    from assistant_desktop.workspace_tools import WORKSPACE_TOOL_DEFINITIONS

    return [*TOOL_DEFINITIONS, *WORKSPACE_TOOL_DEFINITIONS]


def requires_user_approval(name: str) -> bool:
    return name not in AUTO_APPROVED_TOOLS


def describe_tool_call(name: str, arguments: dict[str, Any]) -> str:
    if name.startswith("workspace_") or name == "run_allowed_command":
        from assistant_desktop.workspace_tools import describe_workspace_tool

        return describe_workspace_tool(name, arguments)
    if name == "browser_automate":
        from assistant_desktop.browser_tools import describe_browser_automation

        _check_keys(arguments, {"url", "actions"}, set())
        return describe_browser_automation(
            arguments["url"], arguments["actions"]
        )
    validated = _validate_arguments(name, arguments)
    if name == "open_application":
        app_id = validated["app_id"]
        if app_id == "browser":
            url = validated.get("url", "about:blank")
            return f"Mở trình duyệt mặc định tới: {url}"
        return f"Mở ứng dụng Windows: {app_id}"
    if name == "click":
        return (
            f"Click chuột {validated['button']} tại tọa độ "
            f"(x={validated['x']}, y={validated['y']})."
        )
    if name == "type_text":
        return (
            f"Gõ chính xác nội dung sau vào cửa sổ hiện đang hoạt động:\n\n"
            f"{validated['text']}\n\n"
            "Để hỗ trợ tiếng Việt, nội dung sẽ tạm được đưa vào clipboard; "
            "clipboard văn bản cũ sẽ được khôi phục sau khi dán."
        )
    if name == "read_webpage":
        return f"Đọc nội dung trang web công khai: {validated['url']}"
    return f"Nhấn phím: {validated['key']}"


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    if name.startswith("workspace_") or name == "run_allowed_command":
        from assistant_desktop.workspace_tools import (
            execute_workspace_tool,
            get_workspace_root,
        )

        root = get_workspace_root()
        root.mkdir(parents=True, exist_ok=True)
        return execute_workspace_tool(name, arguments, root)
    if name == "read_webpage":
        from assistant_desktop.browser_tools import read_webpage

        validated = _validate_arguments(name, arguments)
        return read_webpage(validated["url"])
    if name == "browser_automate":
        from assistant_desktop.browser_tools import automate_webpage

        validated = _validate_arguments(name, arguments)
        return automate_webpage(validated["url"], validated["actions"])
    validated = _validate_arguments(name, arguments)
    if name == "open_application":
        app_id = validated["app_id"]
        if app_id == "browser":
            url = validated.get("url", "about:blank")
            try:
                opened = webbrowser.open(url, new=2)
            except (OSError, RuntimeError) as error:
                raise DesktopToolError(
                    f"Không thể mở URL bằng trình duyệt: {error}"
                ) from error
            if not opened:
                raise DesktopToolError("Không thể mở URL bằng trình duyệt.")
            return f"Đã yêu cầu mở trình duyệt tại {url}."

        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise DesktopToolError(
                "Tính năng mở ứng dụng chỉ được hỗ trợ trên Windows."
            )
        try:
            startfile(APPLICATIONS[app_id])
        except OSError as error:
            raise DesktopToolError(
                f"Không thể mở ứng dụng {app_id}: {error}"
            ) from error
        return f"Đã yêu cầu mở ứng dụng {app_id}."

    pyautogui = _get_pyautogui()
    if name == "click":
        width, height = pyautogui.size()
        x, y = validated["x"], validated["y"]
        if not (0 <= x < width and 0 <= y < height):
            raise DesktopToolError(
                f"Tọa độ nằm ngoài màn hình hiện tại ({width}x{height})."
            )
        try:
            pyautogui.click(x=x, y=y, button=validated["button"])
        except (
            pyautogui.FailSafeException,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            raise DesktopToolError(f"Không thể click: {error}") from error
        return f"Đã click tại ({x}, {y})."

    if name == "type_text":
        try:
            _paste_text(pyautogui, validated["text"])
        except (
            pyautogui.FailSafeException,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            raise DesktopToolError(f"Không thể gõ văn bản: {error}") from error
        return f"Đã gõ {len(validated['text'])} ký tự."

    try:
        pyautogui.press(KEYS[validated["key"]])
    except (
        pyautogui.FailSafeException,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        raise DesktopToolError(f"Không thể nhấn phím: {error}") from error
    return f"Đã nhấn phím {validated['key']}."


def _validate_arguments(
    name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DesktopToolError("Tham số tool phải là object.")

    if name == "open_application":
        _check_keys(arguments, {"app_id"}, {"url"})
        app_id = arguments["app_id"]
        if not isinstance(app_id, str) or app_id not in (
            *APPLICATIONS,
            "browser",
        ):
            raise DesktopToolError("Ứng dụng này không nằm trong danh sách cho phép.")
        result: dict[str, Any] = {"app_id": app_id}
        if "url" in arguments:
            if app_id != "browser":
                raise DesktopToolError("Chỉ được truyền URL khi mở browser.")
            result["url"] = _validate_url(arguments["url"])
        return result

    if name == "click":
        _check_keys(arguments, {"x", "y"}, {"button"})
        x, y = arguments["x"], arguments["y"]
        if type(x) is not int or type(y) is not int:
            raise DesktopToolError("Tọa độ click phải là số nguyên.")
        if x < 0 or y < 0:
            raise DesktopToolError("Tọa độ click không được âm.")
        button = arguments.get("button", "left")
        if button not in ("left", "right"):
            raise DesktopToolError("Chỉ hỗ trợ click trái hoặc phải.")
        return {"x": x, "y": y, "button": button}

    if name == "type_text":
        _check_keys(arguments, {"text"}, set())
        text = arguments["text"]
        if not isinstance(text, str) or not text.strip():
            raise DesktopToolError("Nội dung gõ phải là chuỗi không rỗng.")
        if len(text) > MAX_TYPED_CHARACTERS:
            raise DesktopToolError(
                f"Chỉ cho phép gõ tối đa {MAX_TYPED_CHARACTERS} ký tự mỗi lần."
            )
        return {"text": text}

    if name == "press_key":
        _check_keys(arguments, {"key"}, set())
        key = arguments["key"]
        if not isinstance(key, str) or key not in KEYS:
            raise DesktopToolError("Phím này không nằm trong danh sách cho phép.")
        return {"key": key}

    if name == "read_webpage":
        _check_keys(arguments, {"url"}, set())
        from assistant_desktop.browser_tools import validate_public_http_url

        return {"url": validate_public_http_url(arguments["url"])}

    if name == "browser_automate":
        _check_keys(arguments, {"url", "actions"}, set())
        from assistant_desktop.browser_tools import validate_browser_actions

        url, actions = validate_browser_actions(
            arguments["url"], arguments["actions"]
        )
        return {"url": url, "actions": actions}

    raise DesktopToolError(f"Tool không được phép: {name}")


def _validate_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise DesktopToolError("URL không hợp lệ hoặc quá dài.")
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise DesktopToolError("URL không hợp lệ.") from error
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise DesktopToolError(
            "Chỉ chấp nhận URL http/https không chứa thông tin đăng nhập."
        )
    return value


def _check_keys(
    arguments: dict[str, Any], required: set[str], optional: set[str]
) -> None:
    keys = set(arguments)
    if not required <= keys or keys - required - optional:
        raise DesktopToolError("Tham số tool thiếu hoặc có trường không được phép.")


def _get_pyautogui() -> Any:
    try:
        import pyautogui
    except ImportError as error:
        raise DesktopToolError(
            'Thiếu gói desktop. Cài đặt bằng: py -m pip install -e ".[desktop]"'
        ) from error

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.2
    return pyautogui


def _paste_text(pyautogui: Any, text: str) -> None:
    try:
        import pyperclip
    except ImportError as error:
        raise DesktopToolError(
            'Thiếu gói clipboard. Cài đặt bằng: py -m pip install -e ".[desktop]"'
        ) from error

    try:
        previous_text = pyperclip.paste()
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
        finally:
            pyperclip.copy(previous_text)
    except pyperclip.PyperclipException as error:
        raise DesktopToolError(f"Không thể dùng clipboard: {error}") from error
