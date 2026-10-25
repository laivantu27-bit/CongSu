import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from assistant_desktop.speech_output import PiperSpeaker


class PiperSpeakerTests(unittest.TestCase):
    def test_speak_requires_a_voice_path(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "PIPER_VOICE"):
                PiperSpeaker().speak("Xin chào")

    def test_speak_reports_missing_voice_file(self):
        with self.assertRaises(FileNotFoundError):
            PiperSpeaker("missing-voice.onnx").speak("Xin chào")

    def test_speak_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            PiperSpeaker().speak("  ")

    def test_speak_synthesizes_and_plays_piper_audio(self):
        voice = Mock()
        voice.synthesize.return_value = [
            SimpleNamespace(sample_rate=22_050, audio_int16_bytes=b"\x01"),
            SimpleNamespace(sample_rate=22_050, audio_int16_bytes=b"\x02"),
        ]
        piper_module = types.ModuleType("piper")
        piper_module.PiperVoice = SimpleNamespace(load=Mock(return_value=voice))
        numpy_module = types.ModuleType("numpy")
        numpy_module.int16 = "int16"
        numpy_module.frombuffer = Mock(return_value="audio")
        sounddevice_module = types.ModuleType("sounddevice")
        sounddevice_module.play = Mock()

        with tempfile.NamedTemporaryFile(suffix=".onnx") as voice_file:
            with patch.dict(
                sys.modules,
                {
                    "piper": piper_module,
                    "numpy": numpy_module,
                    "sounddevice": sounddevice_module,
                },
            ):
                PiperSpeaker(voice_file.name).speak("Xin chào")

        voice.synthesize.assert_called_once_with("Xin chào")
        numpy_module.frombuffer.assert_called_once_with(b"\x01\x02", dtype="int16")
        sounddevice_module.play.assert_called_once_with(
            "audio", samplerate=22_050, blocking=True
        )


if __name__ == "__main__":
    unittest.main()
