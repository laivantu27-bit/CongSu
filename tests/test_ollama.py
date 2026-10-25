import json
import unittest
from io import BytesIO
from unittest.mock import patch

from assistant_desktop.ollama import (
    OllamaClient,
    OllamaError,
    create_chat_payload,
)


class CreateChatPayloadTests(unittest.TestCase):
    def test_payload_uses_non_streaming_model_and_preserves_vietnamese(self):
        messages = [{"role": "user", "content": "Xin chào, bạn khỏe không?"}]

        payload = create_chat_payload("qwen2.5:7b", messages)

        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertEqual(payload["messages"], messages)
        self.assertFalse(payload["stream"])

    def test_payload_includes_tools_only_when_provided(self):
        messages = [{"role": "user", "content": "Mở Notepad"}]
        tools = [{"type": "function", "function": {"name": "open_application"}}]

        payload = create_chat_payload("qwen2.5:7b", messages, tools)

        self.assertEqual(payload["tools"], tools)
        self.assertNotIn("tools", create_chat_payload("qwen2.5:7b", messages))

    @patch("assistant_desktop.ollama.urlopen")
    def test_chat_extracts_assistant_content(self, urlopen):
        urlopen.return_value = BytesIO(
            b'{"message":{"role":"assistant","content":"Xin ch\xc3\xa0o!"}}'
        )

        answer = OllamaClient().chat(
            [{"role": "user", "content": "Chào"}]
        )

        self.assertEqual(answer, "Xin chào!")

    @patch("assistant_desktop.ollama.urlopen")
    def test_chat_rejects_invalid_response_shape(self, urlopen):
        urlopen.return_value = BytesIO(b"[]")

        with self.assertRaises(OllamaError):
            OllamaClient().chat([{"role": "user", "content": "Hi"}])

    @patch("assistant_desktop.ollama.urlopen")
    def test_chat_message_preserves_tool_calls(self, urlopen):
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "open_application",
                        "arguments": {"app_id": "notepad"},
                    }
                }
            ],
        }
        urlopen.return_value = BytesIO(
            json.dumps({"message": message}).encode("utf-8")
        )

        result = OllamaClient().chat_message(
            [{"role": "user", "content": "Mở Notepad"}],
            tools=[{"type": "function"}],
        )

        self.assertEqual(result, message)
        request = urlopen.call_args.args[0]
        self.assertIn(b'"tools"', request.data)


if __name__ == "__main__":
    unittest.main()
