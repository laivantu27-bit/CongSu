from __future__ import annotations

from threading import Lock
from typing import Any

_model_lock = Lock()
_whisper_model: Any | None = None


class MicrophoneRecorder:
    def __init__(self, sample_rate: int = 16_000) -> None:
        self._sample_rate = sample_rate
        self._stream: Any | None = None
        self._chunks: list[Any] = []
        self._numpy_module: Any | None = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import numpy
        import sounddevice

        if self.is_recording:
            raise RuntimeError("Đang ghi âm.")

        self._chunks = []
        self._numpy_module = numpy

        def capture(indata: Any, *_: Any) -> None:
            self._chunks.append(indata.copy())

        stream = sounddevice.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            callback=capture,
        )
        try:
            stream.start()
        except (OSError, RuntimeError):
            stream.close()
            raise
        self._stream = stream

    def stop(self) -> Any:
        if self._stream is None or self._numpy_module is None:
            raise RuntimeError("Chưa bắt đầu ghi âm.")

        stream = self._stream
        self._stream = None
        try:
            stream.stop()
        finally:
            stream.close()

        if not self._chunks:
            raise RuntimeError("Không thu được âm thanh từ micro.")
        return self._numpy_module.concatenate(self._chunks, axis=0).reshape(-1)


def transcribe_vietnamese(audio: Any) -> str:
    global _whisper_model

    from faster_whisper import WhisperModel

    with _model_lock:
        if _whisper_model is None:
            _whisper_model = WhisperModel(
                "small",
                device="cpu",
                compute_type="int8",
            )
        segments, _ = _whisper_model.transcribe(
            audio,
            language="vi",
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()

    if not text:
        raise RuntimeError("Không nhận dạng được lời nói trong bản ghi.")
    return text
