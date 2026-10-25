# Trợ lý AI desktop

Ứng dụng desktop Python chạy trên Windows, chat tiếng Việt với Ollama local, hỗ trợ trò chuyện đồng cảm, memory dài hạn cục bộ, Playwright đọc web, thao tác workspace giới hạn và MCP server stdio. Không chạy lệnh shell tùy ý.

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

Cài Playwright và trình duyệt Chromium nếu cần đọc trang web:

```powershell
py -m pip install -e ".[browser]"
py -m playwright install chromium
```

Chạy MCP server qua stdio (cần cài extra `mcp`):

```powershell
py -m pip install -e ".[mcp,browser]"
assistant-mcp
```

MCP server dùng stdio và nên được cấu hình trực tiếp trong MCP client đáng tin cậy. Không mở server này ra mạng. Thay đổi qua MCP bị khóa mặc định; chỉ bật từng quyền cần thiết trong environment của tiến trình MCP sau khi bật xác nhận ở client:

```powershell
$env:ASSISTANT_MCP_ALLOW_FILE_WRITE = "true"
$env:ASSISTANT_MCP_ALLOW_FILE_DELETE = "true"
$env:ASSISTANT_MCP_ALLOW_MEMORY_WRITE = "true"
$env:ASSISTANT_MCP_ALLOW_MEMORY_CLEAR = "true"
$env:ASSISTANT_MCP_ALLOW_BROWSER_AUTOMATION = "true"
$env:ASSISTANT_MCP_ALLOW_SYSTEM_COMMANDS = "true"
assistant-mcp
```

Chỉ bật từng quyền cần dùng; không bật các quyền thay đổi dữ liệu nếu MCP client không yêu cầu xác nhận cho từng lần gọi.

Workspace mặc định là `C:\CongSu\workspace`. Có thể thay đổi bằng biến môi trường `ASSISTANT_WORKSPACE`. File tools chỉ thao tác bên trong thư mục này; chỉ đọc UTF-8; giới hạn 1 MB mỗi tệp; xóa chỉ áp dụng cho một file, không xóa thư mục.

Lệnh hệ thống chỉ gồm `python_version`, `git_version` và `ollama_version`, chạy bằng argv cố định, không qua shell và không nhận lệnh tùy ý.

Tải một voice tiếng Việt theo hướng dẫn [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md), sau đó đặt `PIPER_VOICE` tới file `.onnx` của voice đó. Có thể cấu hình endpoint và model Ollama bằng biến môi trường:

```powershell
$env:PIPER_VOICE = "C:\models\vi_VN-voice-medium.onnx"
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen2.5:7b"
py -m assistant_desktop
```

## Hiện có

- Giao diện chat desktop bằng PySide6; lịch sử mở lại qua **Lịch sử**, xóa riêng lịch sử qua **Xóa lịch sử**.
- Ghi âm bằng micro và nhận dạng tiếng Việt bằng faster-whisper; bản ghi được xử lý cục bộ.
- Đọc câu trả lời mới nhất bằng Piper khi bấm nút; cần cài extra `tts` và cấu hình model voice tiếng Việt.
- Agent trò chuyện đồng cảm bằng tiếng Việt, ghi chú một số sở thích/hoạt động được nhận diện từ lời người dùng vào SQLite cục bộ, và đưa ghi chú liên quan vào ngữ cảnh chat. Hội thoại user/assistant được lưu bền vững, có thể mở lại qua **Lịch sử**; **Xóa lịch sử** chỉ xóa hội thoại, không xóa memory. Nút **Xem memory** và **Xóa memory** quản lý memory riêng.
- Agent có thể đề xuất mở Notepad, Calculator, Explorer hoặc Paint; click chuột; gõ tối đa 500 ký tự; và nhấn phím trong danh sách giới hạn.
- Click chuột, gõ tối đa 500 ký tự và nhấn phím trong danh sách cho phép không cần xác nhận; chỉ thực hiện thao tác khi người dùng yêu cầu. Mở ứng dụng vẫn cần xác nhận riêng.
- Playwright có thể đọc văn bản tối đa 12.000 ký tự từ trang công khai http/https; browser headless, không đăng nhập/tải tệp và chặn host nội bộ. Tool `browser_automate` có thể click theo nội dung chính xác, điền trường theo nhãn và nhấn phím allowlist; toàn bộ URL, hành động và nội dung điền được hiển thị trong hộp thoại xác nhận trước khi chạy. Mỗi phiên là context mới, không chia sẻ cookie; cần cài extra `browser` và Chromium.
- Workspace tools liệt kê/đọc tệp; ghi đè và xóa tệp yêu cầu xác nhận trong ứng dụng. File access giới hạn trong `C:\CongSu\workspace` (hoặc `ASSISTANT_WORKSPACE`).
- Tool orchestration kiểm tra toàn bộ kế hoạch trước khi chạy, dừng nếu có thao tác không hợp lệ; tối đa 5 tool call cho mỗi lượt.
- Không chạy lệnh shell tùy ý. Chỉ có lệnh xem phiên bản Python, Git, Ollama trong allowlist; yêu cầu xác nhận trong ứng dụng.
- MCP server stdio expose workspace, browser, memory và lệnh phiên bản allowlist. Các quyền thay đổi dữ liệu, browser automation và lệnh hệ thống đều bị khóa mặc định; chỉ mở riêng bằng biến môi trường nêu trên sau khi cấu hình xác nhận ở MCP client. Không mở server ra mạng.
- Gõ tiếng Việt tạm dùng clipboard Windows; nội dung văn bản trước đó được khôi phục sau thao tác.
- PyAutoGUI fail-safe bật; đưa chuột lên góc trên-trái để hủy thao tác chuột/bàn phím.
- Lần đầu chạy faster-whisper có thể cần tải model nhận dạng về máy.
- Gửi hội thoại tới Ollama API cục bộ; lịch sử tin nhắn được gửi kèm để giữ ngữ cảnh trong phiên.
- Yêu cầu mạng chạy nền để giao diện không bị treo.
- Thông báo lỗi khi Ollama chưa chạy, sai model hoặc kết nối thất bại.
- Nút xóa hội thoại để bắt đầu phiên mới.

Memory và lịch sử dùng `%LOCALAPPDATA%\CongSu\memory.sqlite3`. Tự động lưu chỉ áp dụng các câu có mẫu rõ ràng như “tôi thích ...”, “mình đang học ...”; chuỗi trông như mật khẩu, token, email hoặc số điện thoại bị bỏ qua. Dữ liệu memory liên quan và tối đa 80 tin nhắn gần nhất được gửi tới Ollama cục bộ khi chat; lịch sử cũ hơn vẫn được lưu để mở lại nhưng không đưa hết vào mỗi prompt.
