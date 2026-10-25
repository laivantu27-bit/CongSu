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
        self.assertEqual(len(definitions), 15)
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
        locator.evaluate.return_value = True
        with self.assertRaisesRegex(DesktopToolError, "gửi biểu mẫu"):
            _click_without_form_submission(locator)
        locator.click.assert_not_called()

        locator.evaluate.return_value = False
        _click_without_form_submission(locator)
        locator.click.assert_called_once()

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
