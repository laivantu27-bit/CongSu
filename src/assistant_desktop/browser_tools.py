from __future__ import annotations

import atexit
import ipaddress
import json
import queue
import re
import socket
import threading
from concurrent.futures import Future
from itertools import count
from typing import Any
from urllib.parse import urlsplit

from assistant_desktop.desktop_tools import DesktopToolError

MAX_PAGE_CHARACTERS = 12_000
MAX_BROWSER_ACTIONS = 8
MAX_BROWSER_TABS = 10
PAGE_TIMEOUT_MS = 15_000
ALLOWED_BROWSER_KEYS = {
    "Tab",
    "Escape",
    "Backspace",
    "Delete",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
}
ALLOWED_LOAD_STATES = {"domcontentloaded", "load", "networkidle"}


class _BrowserSession:
    def __init__(self) -> None:
        self._commands: queue.Queue[
            tuple[str, dict[str, Any], Future[Any]] | None
        ] = queue.Queue()
        self._start_lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._startup_error: Exception | None = None
        self._context: Any = None
        self._pages: dict[str, Any] = {}
        self._page_ids: dict[int, str] = {}
        self._next_tab_id = count(1)

    def call(self, operation: str, **arguments: Any) -> Any:
        self._start()
        future: Future[Any] = Future()
        self._commands.put((operation, arguments, future))
        try:
            return future.result()
        except DesktopToolError:
            raise
        except Exception as error:
            raise DesktopToolError(f"Browser operation failed: {error}") from error

    def _start(self) -> None:
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._serve,
                    name="congsu-playwright",
                    daemon=True,
                )
                self._thread.start()
        if not self._ready.wait(timeout=30):
            raise DesktopToolError("Playwright browser did not start within 30 seconds.")
        if self._startup_error is not None:
            if isinstance(self._startup_error, ImportError):
                raise DesktopToolError(
                    'Thiếu Playwright. Cài đặt bằng: py -m pip install -e ".[browser]" '
                    "sau đó chạy: py -m playwright install chromium"
                ) from self._startup_error
            raise DesktopToolError(
                f"Không thể khởi động Playwright browser: {self._startup_error}"
            ) from self._startup_error

    def _serve(self) -> None:
        playwright = None
        browser = None
        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            self._context = browser.new_context(accept_downloads=False)
            self._context.on("page", self._register_page)
        except Exception as error:
            self._startup_error = error
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                request = self._commands.get()
                if request is None:
                    break
                operation, arguments, future = request
                try:
                    future.set_result(self._dispatch(operation, arguments))
                except Exception as error:
                    future.set_exception(error)
        finally:
            try:
                self._context.browser.close()
            finally:
                playwright.stop()

    def _register_page(self, page: Any) -> str:
        page_key = id(page)
        existing = self._page_ids.get(page_key)
        if existing is not None:
            return existing
        tab_id = f"tab-{next(self._next_tab_id)}"
        if len(self._pages) >= MAX_BROWSER_TABS:
            page.close()
            return ""
        self._pages[tab_id] = page
        self._page_ids[page_key] = tab_id
        page.route("**/*", _route_public_read)
        page.on("close", lambda: self._forget_page(tab_id, page_key))
        return tab_id

    def _forget_page(self, tab_id: str, page_key: int) -> None:
        self._pages.pop(tab_id, None)
        self._page_ids.pop(page_key, None)

    def _get_page(self, tab_id: str) -> Any:
        page = self._pages.get(tab_id)
        if page is None or page.is_closed():
            raise DesktopToolError(f"Không tìm thấy tab browser đang mở: {tab_id}")
        return page

    def _dispatch(self, operation: str, arguments: dict[str, Any]) -> Any:
        if operation == "open_browser":
            if len(self._pages) >= MAX_BROWSER_TABS:
                raise DesktopToolError(
                    f"Đã đạt giới hạn {MAX_BROWSER_TABS} tab browser."
                )
            page = self._context.new_page()
            tab_id = self._register_page(page)
            page.goto(
                arguments["url"],
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )
            return self._page_summary(tab_id, page)

        if operation == "list_browser_tabs":
            tabs = []
            for tab_id, page in list(self._pages.items()):
                if page.is_closed():
                    self._forget_page(tab_id, id(page))
                    continue
                tabs.append(
                    {"tab_id": tab_id, "url": page.url, "title": page.title()}
                )
            return tabs

        tab_id = arguments["tab_id"]
        page = self._get_page(tab_id)
        if operation == "read_page":
            body = page.locator("body").inner_text(timeout=PAGE_TIMEOUT_MS)
            warnings = _page_warnings(page.url, page.title(), body)
            return (
                f"Trang: {page.url}\nTiêu đề: {page.title()}\n"
                f"{warnings}\n\n{body[:MAX_PAGE_CHARACTERS]}\n\n"
                f"Phần tử tương tác:\n{_interactive_snapshot(page)}"
            )
        if operation == "navigate_browser":
            page.goto(
                arguments["url"],
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )
            return self._page_summary(tab_id, page)
        if operation == "click_by_text":
            _click_without_form_submission(
                page.get_by_text(arguments["text"], exact=True).first
            )
            return f"Đã click theo nội dung trong {tab_id}; trang hiện tại: {page.url}"
        if operation == "click_selector":
            _click_without_form_submission(
                page.locator(f"css={arguments['selector']}").first
            )
            return f"Đã click selector trong {tab_id}; trang hiện tại: {page.url}"
        if operation == "fill_form":
            _fill_form_field(page, arguments["label"], arguments["value"])
            return f"Đã điền trường '{arguments['label']}' trong {tab_id}."
        if operation == "scroll_page":
            scroll_position = page.evaluate(
                """({direction, amount}) => {
                    window.scrollBy(0, direction === 'down' ? amount : -amount);
                    return Math.round(window.scrollY);
                }""",
                {
                    "direction": arguments["direction"],
                    "amount": arguments["amount"],
                },
            )
            return (
                f"Đã cuộn {arguments['direction']} {arguments['amount']} pixel; "
                f"vị trí hiện tại: {scroll_position}."
            )
        if operation == "wait_for_load":
            page.wait_for_load_state(
                arguments["state"],
                timeout=arguments["timeout_ms"],
            )
            return (
                f"Tab {tab_id} đạt trạng thái {arguments['state']}: "
                f"{page.url}"
            )
        if operation == "close_browser_tab":
            page.close()
            return f"Đã đóng {tab_id}."
        raise DesktopToolError(f"Browser operation không được hỗ trợ: {operation}")

    @staticmethod
    def _page_summary(tab_id: str, page: Any) -> dict[str, str]:
        return {
            "tab_id": tab_id,
            "url": page.url,
            "title": page.title(),
            "message": "Trang đã tải DOM; dùng read_page để đọc hoặc wait_for_load.",
        }

    def close(self) -> None:
        if self._thread is None:
            return
        self._commands.put(None)
        self._thread.join(timeout=20)


_BROWSER_SESSION = _BrowserSession()
atexit.register(_BROWSER_SESSION.close)


def _route_public_read(route: Any) -> None:
    try:
        if route.request.method not in {"GET", "HEAD"}:
            route.abort()
            return
        validate_public_http_url(route.request.url)
    except DesktopToolError:
        route.abort()
    else:
        route.continue_()


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

                page.route("**/*", _route_public_read)
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
            "click_role": {"type", "role", "name"},
            "fill_label": {"type", "label", "value"},
            "select_label": {"type", "label", "value"},
            "check_label": {"type", "label"},
            "uncheck_label": {"type", "label"},
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
        if action_type == "click_role" and action["role"] not in {"button", "link"}:
            raise DesktopToolError("Browser chỉ hỗ trợ role button hoặc link.")
        validated.append(action.copy())
    return validated_url, validated


def describe_browser_automation(url: str, actions: object) -> str:
    validated_url, validated_actions = validate_browser_actions(url, actions)
    descriptions = [f"1. Mở trang {validated_url}"]
    for index, action in enumerate(validated_actions, 2):
        if action["type"] == "click_text":
            description = f"Click phần tử có nội dung chính xác: {action['text']}"
        elif action["type"] == "click_role":
            description = (
                f"Click {action['role']} có tên chính xác: {action['name']}"
            )
        elif action["type"] == "fill_label":
            description = (
                f"Điền '{action['value']}' vào trường '{action['label']}'"
            )
        elif action["type"] == "select_label":
            description = (
                f"Chọn giá trị '{action['value']}' trong danh sách "
                f"'{action['label']}'"
            )
        elif action["type"] == "check_label":
            description = f"Đánh dấu hộp chọn '{action['label']}'"
        elif action["type"] == "uncheck_label":
            description = f"Bỏ đánh dấu hộp chọn '{action['label']}'"
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

                page.route("**/*", _route_public_read)
                page.goto(
                    validated_url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )
                for action in validated_actions:
                    if action["type"] == "click_text":
                        locator = page.get_by_text(action["text"], exact=True).first
                        _click_without_form_submission(locator)
                    elif action["type"] == "click_role":
                        locator = page.get_by_role(
                            action["role"],
                            name=action["name"],
                            exact=True,
                        ).first
                        _click_without_form_submission(locator)
                    elif action["type"] == "fill_label":
                        _fill_form_field(
                            page, action["label"], action["value"]
                        )
                    elif action["type"] == "select_label":
                        page.get_by_label(
                            action["label"], exact=True
                        ).select_option(
                            action["value"],
                            timeout=PAGE_TIMEOUT_MS,
                        )
                    elif action["type"] == "check_label":
                        page.get_by_label(
                            action["label"], exact=True
                        ).check(timeout=PAGE_TIMEOUT_MS)
                    elif action["type"] == "uncheck_label":
                        page.get_by_label(
                            action["label"], exact=True
                        ).uncheck(timeout=PAGE_TIMEOUT_MS)
                    else:
                        page.keyboard.press(action["key"])
                body = page.locator("body").inner_text(timeout=PAGE_TIMEOUT_MS)
                interactive = _interactive_snapshot(page)
                return (
                    f"Trang: {page.url}\nTiêu đề: {page.title()}\n\n"
                    + body[:MAX_PAGE_CHARACTERS]
                    + "\n\nPhần tử tương tác:\n"
                    + interactive
                )
            finally:
                browser.close()
    except PlaywrightError as error:
        raise DesktopToolError(f"Không thể tự động hóa trang web: {error}") from error


def validate_browser_session_tool(
    name: str, arguments: object
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DesktopToolError("Tham số browser phải là object.")
    required_optional = {
        "open_browser": ({"url"}, set()),
        "list_browser_tabs": (set(), set()),
        "read_page": ({"tab_id"}, set()),
        "navigate_browser": ({"tab_id", "url"}, set()),
        "click_by_text": ({"tab_id", "text"}, set()),
        "click_selector": ({"tab_id", "selector"}, set()),
        "fill_form": ({"tab_id", "label", "value"}, set()),
        "scroll_page": ({"tab_id", "direction", "amount"}, set()),
        "wait_for_load": ({"tab_id", "state"}, {"timeout_ms"}),
        "close_browser_tab": ({"tab_id"}, set()),
    }
    allowed = required_optional.get(name)
    if allowed is None:
        raise DesktopToolError(f"Browser tool không được hỗ trợ: {name}")
    required, optional = allowed
    if not required <= arguments.keys() or arguments.keys() - required - optional:
        raise DesktopToolError("Tham số browser thiếu hoặc có trường không hợp lệ.")
    validated = dict(arguments)
    if name in {"open_browser", "navigate_browser"}:
        validated["url"] = validate_public_http_url(validated["url"])
    if name == "list_browser_tabs":
        return validated
    for field in required - {"amount"}:
        value = validated[field]
        if name == "fill_form" and field == "value":
            if not isinstance(value, str) or len(value) > 1000:
                raise DesktopToolError(
                    "Nội dung điền phải là chuỗi tối đa 1.000 ký tự."
                )
            continue
        if not isinstance(value, str) or not value.strip():
            raise DesktopToolError(f"Tham số {field} phải là chuỗi không rỗng.")
        if len(value) > (2048 if field == "url" else 1000):
            raise DesktopToolError(f"Tham số {field} quá dài.")
    if "tab_id" in validated and not re.fullmatch(r"tab-\d+", validated["tab_id"]):
        raise DesktopToolError("tab_id không hợp lệ.")
    if name == "click_selector" and len(validated["selector"]) > 500:
        raise DesktopToolError("CSS selector không được vượt quá 500 ký tự.")
    if name == "fill_form" and len(validated["value"]) > 1000:
        raise DesktopToolError("Nội dung điền không được vượt quá 1.000 ký tự.")
    if name == "scroll_page":
        if validated["direction"] not in {"up", "down"}:
            raise DesktopToolError("Hướng cuộn chỉ nhận up hoặc down.")
        amount = validated["amount"]
        if type(amount) is not int or not 1 <= amount <= 2000:
            raise DesktopToolError("Khoảng cuộn phải là số nguyên từ 1 đến 2.000.")
    if name == "wait_for_load":
        state = validated["state"]
        if state not in ALLOWED_LOAD_STATES:
            raise DesktopToolError("Trạng thái tải trang không được hỗ trợ.")
        timeout_ms = validated.get("timeout_ms", PAGE_TIMEOUT_MS)
        if type(timeout_ms) is not int or not 100 <= timeout_ms <= PAGE_TIMEOUT_MS:
            raise DesktopToolError("Thời gian chờ phải từ 100 đến 15.000 ms.")
        validated["timeout_ms"] = timeout_ms
    return validated


def describe_browser_session_tool(name: str, arguments: object) -> str:
    validated = validate_browser_session_tool(name, arguments)
    if name == "open_browser":
        return f"Mở URL công khai trong Playwright: {validated['url']}"
    if name == "list_browser_tabs":
        return "Liệt kê các tab browser đang mở."
    if name == "read_page":
        return f"Đọc nội dung tab {validated['tab_id']}."
    if name == "navigate_browser":
        return (
            f"Điều hướng tab {validated['tab_id']} tới {validated['url']}."
        )
    if name == "click_by_text":
        return (
            f"Click nội dung chính xác '{validated['text']}' trong "
            f"tab {validated['tab_id']} (không gửi form)."
        )
    if name == "click_selector":
        return (
            f"Click CSS selector '{validated['selector']}' trong "
            f"tab {validated['tab_id']} (không gửi form)."
        )
    if name == "fill_form":
        return (
            f"Điền '{validated['value']}' vào nhãn "
            f"'{validated['label']}' trong tab {validated['tab_id']}."
        )
    if name == "scroll_page":
        return (
            f"Cuộn tab {validated['tab_id']} {validated['direction']} "
            f"{validated['amount']} pixel."
        )
    if name == "wait_for_load":
        return (
            f"Chờ tab {validated['tab_id']} đạt {validated['state']} "
            f"(tối đa {validated['timeout_ms']} ms)."
        )
    return f"Đóng tab browser {validated['tab_id']}."


def execute_browser_session_tool(name: str, arguments: object) -> str:
    validated = validate_browser_session_tool(name, arguments)
    result = _BROWSER_SESSION.call(name, **validated)
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def _page_warnings(url: str, title: str, text: str) -> str:
    combined = f"{url}\n{title}\n{text[:5000]}".casefold()
    warnings = []
    if re.search(r"captcha|recaptcha|verify you are human|are you a robot", combined):
        warnings.append(
            "Cảnh báo: có thể trang đang yêu cầu CAPTCHA; không tự động giải CAPTCHA."
        )
    if re.search(r"/(?:login|log-in|signin|sign-in|auth)(?:[/?#]|$)", url.casefold()) or re.search(
        r"sign in|log in|đăng nhập|mật khẩu", f"{title}\n{text[:3000]}".casefold()
    ):
        warnings.append(
            "Cảnh báo: có thể trang yêu cầu đăng nhập; không tự nhập thông tin đăng nhập."
        )
    return "\n".join(warnings) if warnings else ""


def _click_without_form_submission(locator: Any) -> None:
    element_info = locator.evaluate(
        """
        element => {
            const metadata = [];
            let current = element;
            for (let depth = 0; current && depth < 5; depth++, current = current.parentElement) {
                metadata.push(
                    current.id || '',
                    current.className?.toString() || '',
                    current.getAttribute('aria-label') || '',
                    current.getAttribute('title') || '',
                    depth === 0 ? (current.innerText || '').slice(0, 300) : ''
                );
            }
            const captcha = /captcha|recaptcha|verify (?:that )?you are human|i.?m not a robot/i
                .test(metadata.join(' ').slice(0, 2000));
            const control = element.closest(
                'button, input[type="submit"], input[type="image"]'
            );
            let submit = false;
            if (control && control.form) {
                submit = control.matches('input[type="submit"], input[type="image"]')
                    || (control.getAttribute('type') || 'submit').toLowerCase() === 'submit';
            }
            return {captcha, submit};
        }
        """
    )
    if element_info["captcha"]:
        raise DesktopToolError("Không tương tác với CAPTCHA; yêu cầu người dùng xử lý thủ công.")
    if element_info["submit"]:
        raise DesktopToolError(
            "Không click nút gửi biểu mẫu; chỉ hỗ trợ thao tác không gửi form."
        )
    locator.click(timeout=PAGE_TIMEOUT_MS)


def _fill_form_field(page: Any, label: str, value: str) -> None:
    if re.search(r"/(?:login|log-in|signin|sign-in|auth)(?:[/?#]|$)", page.url.casefold()):
        raise DesktopToolError(
            "Không tự động điền biểu mẫu trên trang đăng nhập."
        )
    locator = page.get_by_label(label, exact=True).first
    field_info = locator.evaluate(
        """
        element => {
            const metadata = [
                element.id || '',
                element.getAttribute('name') || '',
                element.getAttribute('aria-label') || '',
                element.getAttribute('placeholder') || '',
                element.closest('label')?.innerText || ''
            ].join(' ');
            return {
                type: (element.getAttribute('type') || '').toLowerCase(),
                inPasswordForm: Boolean(
                    element.closest('form')?.querySelector('input[type="password"]')
                ),
                captcha: /captcha|recaptcha|verification code|security code|mã xác nhận/i
                    .test(metadata)
            };
        }
        """
    )
    if field_info["type"] in {"password", "file", "hidden"}:
        raise DesktopToolError(
            "Không cho phép điền trường mật khẩu, tệp hoặc ẩn."
        )
    if field_info["inPasswordForm"]:
        raise DesktopToolError(
            "Không tự động điền trường thuộc biểu mẫu đăng nhập."
        )
    if field_info["captcha"]:
        raise DesktopToolError("Không điền trường CAPTCHA hoặc mã xác minh.")
    locator.fill(value, timeout=PAGE_TIMEOUT_MS)


def _interactive_snapshot(page: Any) -> str:
    elements = page.locator(
        "a, button, input, select, textarea"
    ).evaluate_all(
        """
        elements => elements.slice(0, 100).map(element => {
            const type = (element.getAttribute('type') || '').toLowerCase();
            if (type === 'password' || type === 'hidden' || type === 'file') {
                return null;
            }
            const label = element.getAttribute('aria-label')
                || element.innerText
                || element.getAttribute('placeholder')
                || element.getAttribute('name')
                || '';
            const href = element.matches('a') ? element.href : '';
            return {
                tag: element.tagName.toLowerCase(),
                type,
                label: label.trim().slice(0, 120),
                href: href.slice(0, 300),
            };
        }).filter(Boolean)
        """
    )
    return "\n".join(
        " - ".join(
            part
            for part in (
                item["tag"],
                item["type"],
                item["label"],
                item["href"],
            )
            if part
        )
        for item in elements
    )[:4_000] or "(không có phần tử tương tác)"
