"""Fake integration tests for the Phase 3 LiveKit room adapter."""

import asyncio
from types import SimpleNamespace

import pytest

from voice_mode.livekit.config import LiveKitConfig
from voice_mode.livekit.errors import LiveKitDependencyMissingError, LiveKitError
from voice_mode.livekit.models import LiveKitConversationRequest
from voice_mode.livekit import transport


class FakePlugin:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeOpenAI:
    STT = FakePlugin
    TTS = FakePlugin


class FakeVAD:
    calls = []

    @classmethod
    def load(cls, **kwargs):
        cls.calls.append(kwargs)
        return FakePlugin(**kwargs)


class FakeSilero:
    VAD = FakeVAD


class FakeSpeechHandle:
    blocker = None

    async def wait_for_playout(self):
        if self.blocker is not None:
            await self.blocker.wait()


class FakeSession:
    instances = []
    transcript = "browser reply"
    emit_error = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.handlers = {}
        self.closed = False
        self.said = []
        self.__class__.instances.append(self)

    def on(self, event, callback):
        self.handlers[event] = callback

    async def start(self, agent, *, room):
        self.agent = agent
        self.room = room
        if self.emit_error:
            self.handlers["error"](SimpleNamespace())
        elif self.transcript is not None:
            self.handlers["user_input_transcribed"](
                SimpleNamespace(transcript=self.transcript, is_final=True)
            )

    def say(self, message):
        self.said.append(message)
        return FakeSpeechHandle()

    async def aclose(self):
        self.closed = True


class FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAgents:
    AgentSession = FakeSession
    Agent = FakeAgent


class FakeRoomOptions:
    pass


class FakeRoom:
    instances = []

    def __init__(self):
        self.handlers = {}
        self.connected = None
        self.disconnected = False
        self.__class__.instances.append(self)

    def on(self, event, callback):
        self.handlers[event] = callback

    async def connect(self, url, token, *, options):
        self.connected = (url, token, options)

    async def disconnect(self):
        self.disconnected = True


class FakeRTC:
    Room = FakeRoom
    RoomOptions = FakeRoomOptions


class FakeClient:
    instances = []

    def __init__(self, config):
        self.config = config
        self.resolve_request = None
        self.minted_room = None
        self.closed = False
        self.__class__.instances.append(self)

    async def resolve_room(self, request):
        self.resolve_request = request
        return SimpleNamespace(room=SimpleNamespace(name=request.room_name or "vm-only"))

    def mint_agent_token(self, room_name):
        self.minted_room = room_name
        return SimpleNamespace(token="safe-test-token")

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_runtime(monkeypatch, request):
    FakeClient.instances.clear()
    FakeRoom.instances.clear()
    FakeSession.instances.clear()
    FakeVAD.calls.clear()
    FakeSession.transcript = "browser reply"
    FakeSession.emit_error = False
    FakeSpeechHandle.blocker = None
    monkeypatch.setattr(transport, "LiveKitClient", FakeClient)
    if request.node.name != "test_lazy_missing_dependency_is_actionable":
        monkeypatch.setattr(
            transport,
            "_load_livekit_modules",
            lambda: transport._LiveKitModules(
                rtc=FakeRTC,
                agents=FakeAgents,
                openai=FakeOpenAI,
                silero=FakeSilero,
            ),
        )
    monkeypatch.setattr(transport.voice_config, "STT_BASE_URLS", ["http://127.0.0.1:2022/v1"])
    monkeypatch.setattr(transport.voice_config, "TTS_BASE_URLS", ["http://127.0.0.1:8880/v1"])
    monkeypatch.setattr(transport.voice_config, "STT_MODEL", "whisper-test")
    monkeypatch.setattr(transport.voice_config, "TTS_MODELS", ["tts-test"])
    monkeypatch.setattr(transport.voice_config, "TTS_VOICES", ["voice-test"])
    monkeypatch.setattr(transport.voice_config, "OPENAI_API_KEY", None)


def configured():
    return LiveKitConfig(api_key="key", api_secret="secret", room_prefix="vm-")


def test_lazy_missing_dependency_is_actionable(monkeypatch):
    def missing(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(transport.importlib, "import_module", missing)
    with pytest.raises(LiveKitDependencyMissingError) as caught:
        transport._load_livekit_modules()
    assert caught.value.code == "dependency_missing"


@pytest.mark.asyncio
async def test_exact_request_mapping_and_success_transcript():
    result = await transport.converse_livekit(
        LiveKitConversationRequest(
            message="hello room",
            room_name="vm-exact",
            listen_duration_max=4,
            voice="nova",
            tts_model="tts-custom",
            vad_aggressiveness=3,
        ),
        config=configured(),
    )

    client = FakeClient.instances[-1]
    session = FakeSession.instances[-1]
    assert client.resolve_request.room_name == "vm-exact"
    assert client.minted_room == "vm-exact"
    assert session.said == ["hello room"]
    assert session.kwargs["stt"].kwargs["model"] == "whisper-test"
    assert session.kwargs["tts"].kwargs["voice"] == "nova"
    assert session.kwargs["tts"].kwargs["model"] == "tts-custom"
    assert session.kwargs["tts"].kwargs["api_key"] == "dummy-key-for-local"
    assert FakeVAD.calls == [{"activation_threshold": 0.65}]
    assert result.response_text == "browser reply"
    assert result.room_name == "vm-exact"
    assert client.closed and session.closed and FakeRoom.instances[-1].disconnected


@pytest.mark.asyncio
async def test_speak_only_does_not_wait_for_transcript():
    FakeSession.transcript = None
    result = await transport.converse_livekit(
        LiveKitConversationRequest(message="announcement", wait_for_response=False),
        config=configured(),
    )
    assert result.response_text is None
    assert "listen" not in result.timings


@pytest.mark.asyncio
async def test_timeout_returns_no_speech():
    FakeSession.transcript = None
    result = await transport.converse_livekit(
        LiveKitConversationRequest(message="question", listen_duration_max=0.01),
        config=configured(),
    )
    assert result.response_text is None
    assert result.timings["listen"] >= 0.01


@pytest.mark.asyncio
async def test_session_error_is_stable_and_cleanup_runs():
    FakeSession.emit_error = True
    with pytest.raises(LiveKitError) as caught:
        await transport.converse_livekit(
            LiveKitConversationRequest(message="question"),
            config=configured(),
        )
    assert caught.value.code == "session_error"
    assert FakeClient.instances[-1].closed
    assert FakeSession.instances[-1].closed
    assert FakeRoom.instances[-1].disconnected


@pytest.mark.asyncio
async def test_cancellation_propagates_after_cleanup():
    FakeSession.transcript = None
    FakeSpeechHandle.blocker = asyncio.Event()
    task = asyncio.create_task(
        transport.converse_livekit(
            LiveKitConversationRequest(message="long playout"),
            config=configured(),
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert FakeClient.instances[-1].closed
    assert FakeSession.instances[-1].closed
    assert FakeRoom.instances[-1].disconnected
