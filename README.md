# Trợ lý AI desktop

Ứng dụng desktop Python chạy trên Windows, chat tiếng Việt với Ollama local, nhận lời nói bằng faster-whisper, đọc câu trả lời bằng Piper và gọi một số tool desktop có giới hạn. Trợ lý không chạy shell hay tự ý thay đổi file.

## Yêu cầu

- Python 3.10 trở lên
- [Ollama](https://ollama.com/download) đang chạy trên máy
- Một mô hình Ollama, ví dụ `qwen2.5:7b`
- Micro và [PortAudio](https://www.portaudio.com/) cho tính năng ghi âm
- Một model giọng Piper tiếng Việt tải riêng từ [kho voice Piper](https://huggingface.co/rhasspy/piper-voices/tree/main/vi)
- Python packages cho các tính năng voice và desktop

## Cài đặt và chạy

Trong PowerShell tại thư mục dự án:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[voice,tts,desktop]"
ollama pull qwen2.5:7b
py -m assistant_desktop
```

Tải một voice tiếng Việt theo hướng dẫn [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md), sau đó đặt `PIPER_VOICE` tới file `.onnx` của voice đó. Có thể cấu hình endpoint và model Ollama bằng biến môi trường:

```powershell
$env:PIPER_VOICE = "C:\models\vi_VN-voice-medium.onnx"
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen2.5:7b"
py -m assistant_desktop
```

## Hiện có

- Giao diện chat desktop bằng PySide6.
- Ghi âm bằng micro và nhận dạng tiếng Việt bằng faster-whisper; bản ghi được xử lý cục bộ.
- Đọc câu trả lời mới nhất bằng Piper khi bấm nút; cần cài extra `tts` và cấu hình model voice tiếng Việt.
- Agent có thể đề xuất mở Notepad, Calculator, Explorer, Paint hoặc trình duyệt; click chuột; gõ tối đa 500 ký tự; và nhấn một phím trong danh sách giới hạn.
- Mỗi thao tác desktop hiện hộp thoại xác nhận riêng. Dừng nếu từ chối hoặc không xác nhận; tối đa 5 tool call cho mỗi lượt.
- Gõ tiếng Việt tạm dùng clipboard Windows; nội dung văn bản trước đó được khôi phục sau thao tác.
- PyAutoGUI fail-safe bật; đưa chuột lên góc trên-trái để hủy thao tác chuột/bàn phím.
- Lần đầu chạy faster-whisper có thể cần tải model nhận dạng về máy.
- Gửi hội thoại tới Ollama API cục bộ; lịch sử tin nhắn được gửi kèm để giữ ngữ cảnh trong phiên.
- Yêu cầu mạng chạy nền để giao diện không bị treo.
- Thông báo lỗi khi Ollama chưa chạy, sai model hoặc kết nối thất bại.
- Nút xóa hội thoại để bắt đầu phiên mới.

## Lộ trình

1. Chat local, giao diện desktop, STT/TTS tiếng Việt và tool desktop cơ bản có xác nhận (hiện tại).
2. Bổ sung Playwright để thao tác trình duyệt theo trang, vẫn cần xác nhận trước mỗi hành động.
3. Bổ sung thao tác file được giới hạn trong thư mục người dùng cho phép, memory có kiểm soát và MCP khi cần.

Không có tool chạy lệnh hệ thống hoặc thao tác file trong bản hiện tại. Click/gõ chỉ được thực hiện sau xác nhận trong giao diện.
