from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

from assistant_desktop.desktop_tools import DesktopToolError

MAX_PAGE_CHARACTERS = 12_000
PAGE_TIMEOUT_MS = 15_000


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
                page = browser.new_page(java_script_enabled=False)

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
