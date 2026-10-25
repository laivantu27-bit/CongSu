from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any

_voice_lock = Lock()


class PiperSpeaker:
    def __init__(self, voice_path: str | None = None) -> None:
        self._voice_path = voice_path
        self._voice: Any | None = None

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            raise ValueError("Không có nội dung để đọc.")

        voice_path = self._voice_path or os.environ.get("PIPER_VOICE")
        if not voice_path:
            raise RuntimeError(
                "Chưa cấu hình model Piper. Đặt biến PIPER_VOICE tới file "
                ".onnx của giọng tiếng Việt."
            )
        if not Path(voice_path).is_file():
            raise FileNotFoundError(
                f"Không tìm thấy model Piper: {voice_path}"
            )

        import numpy
        import sounddevice

        from piper import PiperVoice

        with _voice_lock:
            if self._voice is None:
                self._voice = PiperVoice.load(voice_path)

        chunks = list(self._voice.synthesize(text))
        if not chunks:
            raise RuntimeError("Piper không tạo được âm thanh.")

        sample_rate = chunks[0].sample_rate
        if any(chunk.sample_rate != sample_rate for chunk in chunks):
            raise RuntimeError(
                "Piper trả về các đoạn âm thanh khác tần số mẫu."
            )
        audio_bytes = b"".join(chunk.audio_int16_bytes for chunk in chunks)
        if not audio_bytes:
            raise RuntimeError("Piper trả về âm thanh rỗng.")

        sounddevice.play(
            numpy.frombuffer(audio_bytes, dtype=numpy.int16),
            samplerate=sample_rate,
            blocking=True,
        )
