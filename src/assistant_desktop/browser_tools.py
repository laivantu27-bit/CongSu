from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

from assistant_desktop.desktop_tools import DesktopToolError

MAX_PAGE_CHARACTERS = 12_000
MAX_BROWSER_ACTIONS = 8
PAGE_TIMEOUT_MS = 15_000
ALLOWED_BROWSER_KEYS = {
    "Enter",
    "Tab",
    "Escape",
    "Backspace",
    "Delete",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
}


def validate_public_http_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise DesktopToolError("URL không hợp lệ hoặc quá dài.")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise DesktopToolError("URL không hợp lệ.") from error
    if (
        parsed.scheme not in ("http", "https")
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise DesktopToolError("Chỉ chấp nhận URL http/https không có thông tin đăng nhập.")
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(
                hostname,
                port or (443 if parsed.scheme == "https" else 80),
            )
        }
    except (OSError, ValueError) as error:
        raise DesktopToolError(f"Không phân giải được máy chủ web: {hostname}") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise DesktopToolError("Không cho phép truy cập địa chỉ mạng nội bộ.")
    return url


def read_webpage(url: str) -> str:
    validated_url = validate_public_http_url(url)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise DesktopToolError(
            'Thiếu Playwright. Cài đặt bằng: py -m pip install -e ".[browser]" '
            "sau đó chạy: py -m playwright install chromium"
        ) from error

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    java_script_enabled=False,
                    accept_downloads=False,
                )

                def guard_request(route: Any) -> None:
                    request_url = route.request.url
                    try:
                        validate_public_http_url(request_url)
                    except DesktopToolError:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", guard_request)
                page.goto(
                    validated_url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
                text = page.locator("body").inner_text(timeout=PAGE_TIMEOUT_MS)
                return text[:MAX_PAGE_CHARACTERS]
            finally:
                browser.close()
    except PlaywrightError as error:
        raise DesktopToolError(f"Không thể đọc trang web: {error}") from error


def validate_browser_actions(url: str, actions: object) -> tuple[str, list[dict[str, str]]]:
    validated_url = validate_public_http_url(url)
    if not isinstance(actions, list) or len(actions) > MAX_BROWSER_ACTIONS:
        raise DesktopToolError(
            f"Browser chỉ nhận tối đa {MAX_BROWSER_ACTIONS} hành động mỗi lần."
        )
    validated: list[dict[str, str]] = []
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("type"), str):
            raise DesktopToolError("Hành động browser không hợp lệ.")
        action_type = action["type"]
        required_fields = {
            "click_text": {"type", "text"},
            "fill_label": {"type", "label", "value"},
            "press_key": {"type", "key"},
        }.get(action_type)
        if required_fields is None or set(action) != required_fields:
            raise DesktopToolError("Hành động browser thiếu hoặc có trường không hợp lệ.")
        for field in required_fields - {"type"}:
            if not isinstance(action[field], str) or not action[field].strip():
                raise DesktopToolError(f"Trường {field} phải là chuỗi không rỗng.")
            if len(action[field]) > 500:
                raise DesktopToolError(f"Trường {field} vượt quá 500 ký tự.")
        if action_type == "press_key" and action["key"] not in ALLOWED_BROWSER_KEYS:
            raise DesktopToolError("Phím browser không nằm trong danh sách cho phép.")
        validated.append(action.copy())
    return validated_url, validated


def describe_browser_automation(url: str, actions: object) -> str:
    validated_url, validated_actions = validate_browser_actions(url, actions)
    descriptions = [f"1. Mở trang {validated_url}"]
    for index, action in enumerate(validated_actions, 2):
        if action["type"] == "click_text":
            description = f"Click phần tử có nội dung chính xác: {action['text']}"
        elif action["type"] == "fill_label":
            description = (
                f"Điền '{action['value']}' vào trường '{action['label']}'"
            )
        else:
            description = f"Nhấn phím {action['key']}"
        descriptions.append(f"{index}. {description}")
    return "Tự động hóa browser (không đăng nhập, không tải tệp):\n" + "\n".join(
        descriptions
    )


def automate_webpage(url: str, actions: object) -> str:
    validated_url, validated_actions = validate_browser_actions(url, actions)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise DesktopToolError(
            'Thiếu Playwright. Cài đặt bằng: py -m pip install -e ".[browser]" '
            "sau đó chạy: py -m playwright install chromium"
        ) from error

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(accept_downloads=False)
                page = context.new_page()
                page.on("popup", lambda popup: popup.close())

                def guard_request(route: Any) -> None:
                    try:
                        validate_public_http_url(route.request.url)
                    except DesktopToolError:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", guard_request)
                page.goto(
                    validated_url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
                for action in validated_actions:
                    if action["type"] == "click_text":
                        page.get_by_text(action["text"], exact=True).first.click(
                            timeout=PAGE_TIMEOUT_MS
                        )
                    elif action["type"] == "fill_label":
                        page.get_by_label(action["label"], exact=True).fill(
                            action["value"],
                            timeout=PAGE_TIMEOUT_MS,
                        )
                    else:
                        page.keyboard.press(action["key"])
                body = page.locator("body").inner_text(timeout=PAGE_TIMEOUT_MS)
                return (
                    f"Trang: {page.url}\nTiêu đề: {page.title()}\n\n"
                    + body[:MAX_PAGE_CHARACTERS]
                )
            finally:
                browser.close()
    except PlaywrightError as error:
        raise DesktopToolError(f"Không thể tự động hóa trang web: {error}") from error
