from __future__ import annotations

import os
import sys
from typing import Any

from PySide6.QtCore import QEvent, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assistant_desktop.agent import AgentWorker, ToolApprovalRequest
from assistant_desktop.ollama import OllamaClient
from assistant_desktop.speech_output import PiperSpeaker
from assistant_desktop.voice import MicrophoneRecorder, transcribe_vietnamese

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thân thiện, biết lắng nghe và trò chuyện tự nhiên bằng "
    "tiếng Việt. Trả lời chân thành, tôn trọng cảm xúc; không giả vờ là con "
    "người. Bạn chỉ có thể thực hiện các thao tác desktop được cung cấp dưới "
    "dạng tool; mỗi thao tác đều cần người dùng xác nhận trong hộp thoại. Chỉ "
    "đề xuất thao tác khi người dùng yêu cầu, không chạy lệnh shell, không "
    "mở ứng dụng ngoài danh sách, và không tuyên bố đã làm nếu tool chưa xác nhận."
)


class SpeechWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, audio: object) -> None:
        super().__init__()
        self._audio = audio

    def run(self) -> None:
        try:
            self.succeeded.emit(transcribe_vietnamese(self._audio))
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            self.failed.emit(f"Không nhận dạng được giọng nói: {error}")


class SpeechOutputWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, speaker: PiperSpeaker, text: str) -> None:
        super().__init__()
        self._speaker = speaker
        self._text = text

    def run(self) -> None:
        try:
            self._speaker.speak(self._text)
            self.succeeded.emit()
        except (
            ImportError,
            FileNotFoundError,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            self.failed.emit(f"Không phát được giọng nói: {error}")


class AssistantWindow(QMainWindow):
    def __init__(self, client: OllamaClient) -> None:
        super().__init__()
        self._client = client
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._worker: QThread | None = None
        self._recorder = MicrophoneRecorder()
        self._speaker = PiperSpeaker()
        self._latest_reply = ""
        self._is_recording = False

        self.setWindowTitle("Trợ lý AI desktop")
        self.resize(760, 620)

        self._transcript = QTextBrowser()
        self._transcript.setOpenExternalLinks(True)
        self._transcript.setPlaceholderText(
            "Bắt đầu trò chuyện bằng tiếng Việt..."
        )
        self._input = QTextEdit()
        self._input.setPlaceholderText("Nhập tin nhắn... (Ctrl+Enter để gửi)")
        self._input.setFixedHeight(90)
        self._input.installEventFilter(self)

        self._status = QLabel("Sẵn sàng")
        self._send_button = QPushButton("Gửi")
        self._send_button.clicked.connect(self._send_message)
        self._voice_button = QPushButton("Thu âm")
        self._voice_button.setToolTip(
            "Bấm để bắt đầu ghi; bấm lần nữa để dừng và nhận dạng tiếng Việt."
        )
        self._voice_button.clicked.connect(self._toggle_recording)
        self._clear_button = QPushButton("Cuộc trò chuyện mới")
        self._clear_button.clicked.connect(self._clear_conversation)
        self._speak_button = QPushButton("Đọc câu trả lời")
        self._speak_button.setEnabled(False)
        self._speak_button.clicked.connect(self._speak_latest_reply)

        buttons = QHBoxLayout()
        buttons.addWidget(self._status, 1)
        buttons.addWidget(self._speak_button)
        buttons.addWidget(self._clear_button)
        buttons.addWidget(self._voice_button)
        buttons.addWidget(self._send_button)

        layout = QVBoxLayout()
        layout.addWidget(self._transcript, 1)
        layout.addWidget(self._input)
        layout.addLayout(buttons)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self._append_message(
            "Trợ lý",
            "Xin chào! Mình có thể trò chuyện với bạn bằng tiếng Việt. "
            "Hãy nhập tin nhắn bên dưới.",
        )

    def eventFilter(self, watched: object, event: object) -> bool:
        if (
            watched is self._input
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._send_message()
            return True
        return super().eventFilter(watched, event)

    def _send_message(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or self._worker is not None or self._is_recording:
            return

        self._input.clear()
        self._messages.append({"role": "user", "content": text})
        self._append_message("Bạn", text)
        self._set_busy(True, "Đang suy nghĩ...")

        self._worker = AgentWorker(self._client, self._messages.copy())
        self._worker.succeeded.connect(self._on_agent_reply)
        self._worker.failed.connect(self._on_error)
        self._worker.approval_requested.connect(self._confirm_tool_action)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _toggle_recording(self) -> None:
        if self._worker is not None:
            return
        if not self._is_recording:
            try:
                self._recorder.start()
            except ImportError:
                self._append_message(
                    "Lỗi micro",
                    'Thiếu gói ghi âm. Cài đặt bằng: py -m pip install -e ".[voice]"',
                )
                self._status.setText("Thiếu gói ghi âm")
                return
            except (OSError, RuntimeError) as error:
                self._append_message("Lỗi micro", str(error))
                self._status.setText("Không thể ghi âm")
                return
            self._is_recording = True
            self._voice_button.setText("Dừng ghi âm")
            self._set_busy(True, "Đang ghi âm...")
            return

        try:
            audio = self._recorder.stop()
        except (OSError, RuntimeError, ValueError) as error:
            self._is_recording = False
            self._voice_button.setText("Thu âm")
            self._set_busy(False, "Không thể ghi âm")
            self._append_message("Lỗi micro", str(error))
            return

        self._is_recording = False
        self._voice_button.setText("Thu âm")
        self._set_busy(True, "Đang nhận dạng tiếng Việt...")
        self._worker = SpeechWorker(audio)
        self._worker.succeeded.connect(self._on_transcription)
        self._worker.failed.connect(self._on_speech_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_transcription(self, text: str) -> None:
        self._input.setReadOnly(False)
        self._input.setPlainText(text)
        self._status.setText("Đã nhận dạng — kiểm tra rồi bấm Gửi")

    def _on_speech_error(self, error: str) -> None:
        self._append_message("Lỗi nhận dạng", error)
        self._status.setText("Không thể nhận dạng")

    def _on_agent_reply(
        self, response: str, messages: list[dict[str, Any]]
    ) -> None:
        self._messages = messages
        self._latest_reply = response
        self._speak_button.setEnabled(True)
        self._append_message("Trợ lý", response)
        self._status.setText("Sẵn sàng")

    def _confirm_tool_action(self, request: ToolApprovalRequest) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Xác nhận thao tác máy tính")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(request.description)
        dialog.setInformativeText(
            "Chỉ cho phép nếu nội dung đúng với điều bạn vừa yêu cầu."
        )
        allow_button = dialog.addButton(
            "Cho phép", QMessageBox.ButtonRole.AcceptRole
        )
        deny_button = dialog.addButton(
            "Từ chối", QMessageBox.ButtonRole.RejectRole
        )
        dialog.setDefaultButton(deny_button)
        dialog.exec()
        request.resolve(dialog.clickedButton() is allow_button)

    def _speak_latest_reply(self) -> None:
        if not self._latest_reply or self._worker is not None:
            return
        self._set_busy(True, "Đang tạo và phát giọng nói...")
        self._worker = SpeechOutputWorker(self._speaker, self._latest_reply)
        self._worker.succeeded.connect(self._on_speech_output_finished)
        self._worker.failed.connect(self._on_speech_output_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_speech_output_finished(self) -> None:
        self._status.setText("Đã đọc xong")

    def _on_speech_output_error(self, error: str) -> None:
        self._append_message("Lỗi giọng nói", error)
        self._status.setText("Không thể phát giọng nói")

    def _on_error(
        self, error: str, messages: list[dict[str, Any]]
    ) -> None:
        self._messages = messages
        self._append_message("Lỗi", error)
        self._status.setText("Không thể kết nối")

    def _on_worker_finished(self) -> None:
        self._set_busy(False, self._status.text())
        self._worker = None

    def _clear_conversation(self) -> None:
        if self._worker is not None or self._is_recording:
            return
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._latest_reply = ""
        self._transcript.clear()
        self._speak_button.setEnabled(False)
        self._append_message(
            "Trợ lý", "Cuộc trò chuyện mới đã sẵn sàng. Bạn muốn chia sẻ điều gì?"
        )
        self._status.setText("Sẵn sàng")

    def _set_busy(self, busy: bool, status: str) -> None:
        self._send_button.setEnabled(not busy)
        self._input.setReadOnly(busy)
        self._clear_button.setEnabled(not busy and not self._is_recording)
        self._voice_button.setEnabled(not busy or self._is_recording)
        self._speak_button.setEnabled(not busy and bool(self._latest_reply))
        self._status.setText(status)

    def _append_message(self, speaker: str, text: str) -> None:
        safe_text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        self._transcript.append(f"<b>{speaker}:</b><br>{safe_text}<br>")
        self._transcript.verticalScrollBar().setValue(
            self._transcript.verticalScrollBar().maximum()
        )


def main() -> None:
    app = QApplication(sys.argv)
    client = OllamaClient(
        host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
    )
    window = AssistantWindow(client)
    window.show()
    sys.exit(app.exec())
