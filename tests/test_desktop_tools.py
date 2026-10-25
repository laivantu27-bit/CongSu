import types
import unittest
from unittest.mock import Mock, patch

from assistant_desktop.desktop_tools import (
    DesktopToolError,
    describe_tool_call,
    execute_tool,
    get_tool_definitions,
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
        self.assertEqual(len(definitions), 4)
        for definition in definitions:
            self.assertFalse(
                definition["function"]["parameters"]["additionalProperties"]
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
