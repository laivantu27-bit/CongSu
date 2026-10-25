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
    def test_basic_desktop_tools_run_without_approval(self):
        tool_calls = [
            ("click", {"x": 10, "y": 20}),
            ("type_text", {"text": "Xin chào"}),
            ("press_key", {"key": "enter"}),
        ]
        for name, arguments in tool_calls:
            with self.subTest(tool=name):
                client = FakeOllamaClient(
                    [
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": name,
                                        "arguments": arguments,
                                    }
                                }
                            ],
                        },
                        {"role": "assistant", "content": "Đã thực hiện."},
                    ]
                )
                worker = AgentWorker(
                    client, [{"role": "user", "content": "Thực hiện"}]
                )
                approval_requests = []
                worker.approval_requested.connect(approval_requests.append)

                with patch(
                    "assistant_desktop.agent.execute_tool",
                    return_value="Thành công.",
                ) as execute_tool:
                    response = worker._run_agent()

                self.assertEqual(response, "Đã thực hiện.")
                execute_tool.assert_called_once_with(name, arguments)
                self.assertEqual(approval_requests, [])

    def test_memory_context_is_sent_to_model_without_persisting_in_history(self):
        client = FakeOllamaClient(
            [{"role": "assistant", "content": "Mình nhớ bạn thích phở."}]
        )
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Bạn nhớ món tôi thích không?"},
        ]
        worker = AgentWorker(
            client,
            messages.copy(),
            memory_context="preference: món phở",
        )

        self.assertEqual(worker._run_agent(), "Mình nhớ bạn thích phở.")
        model_messages = client.calls[0][0]
        self.assertEqual(model_messages[1]["role"], "user")
        self.assertIn("preference: món phở", model_messages[1]["content"])
        self.assertEqual(len(worker._messages), len(messages) + 1)
        self.assertFalse(
            any(
                "preference: món phở" in message.get("content", "")
                for message in worker._messages
            )
        )

    def test_invalid_tool_call_preflight_prevents_partial_execution(self):
        client = FakeOllamaClient(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "click",
                                "arguments": {"x": 10, "y": 20},
                            }
                        },
                        {
                            "function": {
                                "name": "run_shell",
                                "arguments": {"command": "whoami"},
                            }
                        },
                    ],
                }
            ]
        )
        worker = AgentWorker(
            client, [{"role": "user", "content": "Thực hiện"}]
        )

        with patch("assistant_desktop.agent.execute_tool") as execute_tool:
            response = worker._run_agent()

        self.assertIn("không hợp lệ", response)
        execute_tool.assert_not_called()

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
                                "name": "open_application",
                                "arguments": {"app_id": "notepad"},
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
