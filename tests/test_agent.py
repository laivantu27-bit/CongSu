import unittest
from unittest.mock import patch

from assistant_desktop.agent import AgentWorker


class FakeOllamaClient:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def chat_message(self, messages, tools=None):
        self.calls.append((messages, tools))
        return next(self._responses)


class AgentWorkerTests(unittest.TestCase):
    def test_approved_tool_runs_then_model_returns_reply(self):
        client = FakeOllamaClient(
            [
                {
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
                },
                {"role": "assistant", "content": "Đã mở Notepad."},
            ]
        )
        worker = AgentWorker(
            client, [{"role": "user", "content": "Mở Notepad"}]
        )
        worker.approval_requested.connect(
            lambda request: request.resolve(True)
        )

        with patch(
            "assistant_desktop.agent.execute_tool",
            return_value="Đã yêu cầu mở ứng dụng notepad.",
        ) as execute_tool:
            response = worker._run_agent()

        self.assertEqual(response, "Đã mở Notepad.")
        execute_tool.assert_called_once_with(
            "open_application", {"app_id": "notepad"}
        )
        self.assertEqual(worker._messages[-2]["role"], "tool")
        self.assertEqual(worker._messages[-1]["content"], "Đã mở Notepad.")

    def test_denied_tool_does_not_execute(self):
        client = FakeOllamaClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "type_text",
                                "arguments": {"text": "Xin chào"},
                            }
                        }
                    ],
                }
            ]
        )
        worker = AgentWorker(
            client, [{"role": "user", "content": "Gõ Xin chào"}]
        )
        worker.approval_requested.connect(
            lambda request: request.resolve(False)
        )

        with patch("assistant_desktop.agent.execute_tool") as execute_tool:
            response = worker._run_agent()

        self.assertIn("không có xác nhận", response)
        execute_tool.assert_not_called()
        self.assertEqual(worker._messages[-2]["role"], "tool")


if __name__ == "__main__":
    unittest.main()
