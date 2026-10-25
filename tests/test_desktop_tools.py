import types
import unittest
from unittest.mock import Mock, patch

from assistant_desktop.desktop_tools import (
    DesktopToolError,
    describe_tool_call,
    execute_tool,
    get_tool_definitions,
    requires_user_approval,
)


class DesktopToolValidationTests(unittest.TestCase):
    def test_open_application_is_restricted_to_allowlist(self):
        self.assertEqual(
            describe_tool_call("open_application", {"app_id": "notepad"}),
            "Mở ứng dụng Windows: notepad",
        )
        with self.assertRaises(DesktopToolError):
            describe_tool_call(
                "open_application",
                {"app_id": "powershell", "url": "http://example.com"},
            )

    def test_browser_rejects_non_http_url_and_credentials(self):
        with self.assertRaises(DesktopToolError):
            describe_tool_call(
                "open_application",
                {"app_id": "browser", "url": "file:///C:/secret.txt"},
            )
        with self.assertRaises(DesktopToolError):
            describe_tool_call(
                "open_application",
                {
                    "app_id": "browser",
                    "url": "https://user:password@example.com",
                },
            )

    def test_type_text_is_bounded_and_confirmation_shows_clipboard_behavior(self):
        description = describe_tool_call(
            "type_text", {"text": "Xin chào desktop"}
        )
        self.assertIn("Xin chào desktop", description)
        self.assertIn("clipboard văn bản cũ sẽ được khôi phục", description)
        with self.assertRaises(DesktopToolError):
            describe_tool_call("type_text", {"text": "x" * 501})

    def test_click_rejects_bool_and_extra_arguments(self):
        with self.assertRaises(DesktopToolError):
            describe_tool_call("click", {"x": True, "y": 5})
        with self.assertRaises(DesktopToolError):
            describe_tool_call("click", {"x": 5, "y": 5, "clicks": 3})

    def test_unknown_tool_is_rejected(self):
        with self.assertRaises(DesktopToolError):
            describe_tool_call("run_shell", {"command": "whoami"})

    def test_tool_definitions_forbid_extra_arguments(self):
        definitions = get_tool_definitions()
        self.assertEqual(len(definitions), 25)
        names = [definition["function"]["name"] for definition in definitions]
        self.assertEqual(len(names), len(set(names)))
        for definition in definitions:
            self.assertFalse(
                definition["function"]["parameters"]["additionalProperties"]
            )

    def test_confirmation_policy_preserves_sensitive_action_prompts(self):
        self.assertFalse(requires_user_approval("click"))
        self.assertFalse(requires_user_approval("workspace_read"))
        self.assertTrue(requires_user_approval("workspace_write"))
        self.assertTrue(requires_user_approval("workspace_delete"))
        self.assertTrue(requires_user_approval("run_allowed_command"))
        self.assertTrue(requires_user_approval("open_application"))
        self.assertTrue(requires_user_approval("browser_automate"))
        self.assertFalse(requires_user_approval("read_page"))
        self.assertFalse(requires_user_approval("list_browser_tabs"))
        self.assertFalse(requires_user_approval("wait_for_load"))
        self.assertTrue(requires_user_approval("open_browser"))
        self.assertTrue(requires_user_approval("click_selector"))
        self.assertTrue(requires_user_approval("fill_form"))
        self.assertTrue(requires_user_approval("close_browser_tab"))

    def test_browser_session_tools_validate_urls_and_bound_actions(self):
        with patch(
            "assistant_desktop.browser_tools.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            self.assertIn(
                "https://example.com",
                describe_tool_call(
                    "open_browser", {"url": "https://example.com"}
                ),
            )
            self.assertIn(
                "textarea",
                describe_tool_call(
                    "click_selector",
                    {"tab_id": "tab-1", "selector": "textarea"},
                ),
            )
        with patch(
            "assistant_desktop.browser_tools.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        ):
            with self.assertRaises(DesktopToolError):
                describe_tool_call(
                    "navigate_browser",
                    {"tab_id": "tab-1", "url": "http://localhost"},
                )
        with self.assertRaises(DesktopToolError):
            describe_tool_call(
                "scroll_page",
                {"tab_id": "tab-1", "direction": "down", "amount": 2001},
            )
        with self.assertRaises(DesktopToolError):
            describe_tool_call(
                "wait_for_load",
                {"tab_id": "tab-1", "state": "commit"},
            )
        with self.assertRaises(DesktopToolError):
            describe_tool_call(
                "fill_form",
                {"tab_id": "tab-1", "label": "Email", "value": "x" * 1001},
            )

    def test_browser_page_warnings_flag_login_and_captcha_without_bypassing(self):
        from assistant_desktop.browser_tools import _page_warnings

        self.assertIn(
            "CAPTCHA",
            _page_warnings(
                "https://example.com/challenge",
                "Verify you are human",
                "captcha",
            ),
        )
        self.assertIn(
            "đăng nhập",
            _page_warnings(
                "https://example.com/login",
                "Sign in",
                "Enter your password",
            ),
        )
        self.assertEqual(
            _page_warnings("https://example.com", "Example", "Public page"),
            "",
        )

    def test_browser_automation_requires_validated_confirmable_actions(self):
        from assistant_desktop.browser_tools import validate_browser_actions

        with patch(
            "assistant_desktop.browser_tools.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            url, actions = validate_browser_actions(
                "https://example.com",
                [
                    {"type": "fill_label", "label": "Email", "value": "test"},
                    {"type": "click_text", "text": "Continue"},
                ],
            )
            self.assertEqual(url, "https://example.com")
            self.assertEqual(len(actions), 2)
            describe_tool_call(
                "browser_automate",
                {
                    "url": url,
                    "actions": [
                        {"type": "click_text", "text": "Continue"}
                    ],
                },
            )
            with self.assertRaises(DesktopToolError):
                validate_browser_actions(
                    "https://example.com",
                    [{"type": "press_key", "key": "Alt+F4"}],
                )
            with self.assertRaises(DesktopToolError):
                validate_browser_actions(
                    "https://example.com",
                    [{"type": "press_key", "key": "Enter"}],
                )

    def test_browser_automation_does_not_click_submit_controls(self):
        from assistant_desktop.browser_tools import _click_without_form_submission

        locator = Mock()
        locator.evaluate.return_value = {"captcha": False, "submit": True}
        with self.assertRaisesRegex(DesktopToolError, "gửi biểu mẫu"):
            _click_without_form_submission(locator)
        locator.click.assert_not_called()

        locator.evaluate.return_value = {"captcha": False, "submit": False}
        _click_without_form_submission(locator)
        locator.click.assert_called_once()

        locator.evaluate.return_value = {"captcha": True, "submit": False}
        with self.assertRaisesRegex(DesktopToolError, "CAPTCHA"):
            _click_without_form_submission(locator)
        self.assertEqual(locator.click.call_count, 1)

    def test_browser_form_fill_blocks_login_and_captcha_fields(self):
        from assistant_desktop.browser_tools import _fill_form_field

        locator = Mock()
        page = Mock()
        page.url = "https://example.com/search"
        page.get_by_label.return_value.first = locator
        locator.evaluate.return_value = {
            "type": "text",
            "inPasswordForm": True,
            "captcha": False,
        }
        with self.assertRaisesRegex(DesktopToolError, "đăng nhập"):
            _fill_form_field(page, "Username", "account")
        locator.fill.assert_not_called()

        locator.evaluate.return_value = {
            "type": "text",
            "inPasswordForm": False,
            "captcha": True,
        }
        with self.assertRaisesRegex(DesktopToolError, "CAPTCHA"):
            _fill_form_field(page, "Verification", "answer")
        locator.fill.assert_not_called()

        locator.evaluate.return_value = {
            "type": "text",
            "inPasswordForm": False,
            "captcha": False,
        }
        _fill_form_field(page, "Search", "query")
        locator.fill.assert_called_once_with("query", timeout=15000)

        page.url = "https://example.com/login"
        locator.fill.reset_mock()
        with self.assertRaisesRegex(DesktopToolError, "đăng nhập"):
            _fill_form_field(page, "Email", "account@example.com")
        locator.fill.assert_not_called()

    def test_browser_tool_accepts_public_http_url_only(self):
        with patch(
            "assistant_desktop.browser_tools.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            self.assertEqual(
                describe_tool_call(
                    "read_webpage", {"url": "https://example.com"}
                ),
                "Đọc nội dung trang web công khai: https://example.com",
            )
        with patch(
            "assistant_desktop.browser_tools.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        ):
            with self.assertRaisesRegex(DesktopToolError, "mạng nội bộ"):
                describe_tool_call(
                    "read_webpage", {"url": "http://localhost"}
                )

    @patch("assistant_desktop.desktop_tools._get_pyautogui")
    def test_click_uses_validated_screen_coordinates(self, get_pyautogui):
        pyautogui = types.SimpleNamespace(
            size=Mock(return_value=(1280, 720)),
            click=Mock(),
        )
        get_pyautogui.return_value = pyautogui

        result = execute_tool("click", {"x": 20, "y": 30})

        self.assertEqual(result, "Đã click tại (20, 30).")
        pyautogui.click.assert_called_once_with(x=20, y=30, button="left")
        with self.assertRaises(DesktopToolError):
            execute_tool("click", {"x": 1280, "y": 30})


if __name__ == "__main__":
    unittest.main()
