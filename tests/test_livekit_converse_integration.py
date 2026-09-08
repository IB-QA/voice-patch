"""Thin integration guards between converse and LiveKit transport."""

import builtins
import importlib
from unittest.mock import AsyncMock

import pytest

from voice_mode.livekit.models import LiveKitConversationResult

converse_module = importlib.import_module("voice_mode.tools.converse")


@pytest.mark.asyncio
async def test_livekit_dispatch_precedes_local_audio_initialization(monkeypatch):
    fake_result = LiveKitConversationResult(
        response_text="heard in browser",
        room_name="vm-exact",
        stt_provider="whisper",
        tts_provider="kokoro",
        stt_model="whisper-1",
        tts_model="tts-1",
        voice="af_sky",
        timings={"playout": 0.2, "listen": 0.3, "total": 0.5},
    )
    livekit_call = AsyncMock(return_value=fake_result)
    startup = AsyncMock(side_effect=AssertionError("local startup was reached"))

    monkeypatch.setattr(converse_module, "CONCH_ENABLED", False)
    monkeypatch.setattr(converse_module, "get_event_logger", lambda: None)
    monkeypatch.setattr(converse_module, "startup_initialization", startup)
    monkeypatch.setattr(converse_module.sd, "_terminate", lambda: pytest.fail("sounddevice probed"))
    monkeypatch.setattr(converse_module.sd, "_initialize", lambda: pytest.fail("sounddevice probed"))
    monkeypatch.setattr(
        "voice_mode.livekit.transport.converse_livekit",
        livekit_call,
    )

    result = await converse_module._converse_core(
        message="hello",
        transport="livekit",
        room_name="vm-exact",
        skip_conch=True,
    )

    assert result.startswith("Voice response: heard in browser")
    request = livekit_call.await_args.args[0]
    assert request.message == "hello"
    assert request.room_name == "vm-exact"
    startup.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_path_does_not_import_livekit(monkeypatch):
    original_import = builtins.__import__

    def reject_livekit(name, *args, **kwargs):
        if name.startswith("voice_mode.livekit"):
            raise AssertionError(f"local transport imported {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(converse_module, "CONCH_ENABLED", False)
    monkeypatch.setattr(converse_module, "get_event_logger", lambda: None)
    monkeypatch.setattr(
        converse_module.voice_mode.config,
        "FFMPEG_AVAILABLE",
        False,
        raising=False,
    )
    monkeypatch.setattr(builtins, "__import__", reject_livekit)

    result = await converse_module._converse_core(
        message="hello",
        transport="local",
        skip_conch=True,
    )
    assert "FFmpeg is required" in result


@pytest.mark.asyncio
async def test_livekit_turns_rejection_is_structured():
    result = await converse_module._converse_core(
        turns=[{"say": "one"}],
        transport="livekit",
    )
    assert result.startswith("Error [livekit:turns_unsupported]")
