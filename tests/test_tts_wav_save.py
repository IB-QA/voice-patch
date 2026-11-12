"""Saving TTS audio must not leave a locked temp file behind (Windows)."""

import io
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from voice_mode.streaming import _pcm_to_wav_bytes


def test_pcm_becomes_a_valid_wav():
    pcm = (b"\x01\x00" * 2400)
    wav_bytes = _pcm_to_wav_bytes(pcm, 24000)

    with wave.open(io.BytesIO(wav_bytes)) as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24000
        assert wav.getnframes() == 2400


def test_no_temp_file_is_created():
    """The old code created a temp file and deleted it while still open, which
    Windows refuses with 'being used by another process'."""
    with patch.object(tempfile, "NamedTemporaryFile",
                      side_effect=AssertionError("temp file used")):
        _pcm_to_wav_bytes(b"\x00\x00" * 100, 24000)


def test_streaming_has_no_open_then_unlink_pattern():
    source = (Path(__file__).parent.parent / "voice_mode" / "streaming.py").read_text()
    assert "NamedTemporaryFile" not in source
