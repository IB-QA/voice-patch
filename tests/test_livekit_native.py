"""Native LiveKit human-participant join."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from voice_mode.livekit.client import LiveKitClient, MAX_NATIVE_TOKEN_TTL
from voice_mode.livekit.errors import LiveKitError
from voice_mode.livekit.models import ParticipantKind
from voice_mode.livekit.native import (
    DEFAULT_NATIVE_ROOM,
    join_native_room,
    read_native_session,
)

from tests.test_livekit_foundation import configured

pytest_plugins = ["tests.test_livekit_foundation"]


class FakePlatformAudio:
    def __init__(self):
        self.closed = False
        self.source = SimpleNamespace(closed=False)

        def close():
            self.source.closed = True

        self.source.close = close

    def create_audio_source(self):
        return self.source

    def close(self):
        self.closed = True


class FakeLocalAudioTrack:
    @staticmethod
    def create_audio_track(name, source):
        return SimpleNamespace(name=name, source=source)


class FakeRoom:
    instances = []

    def __init__(self):
        self.handlers = {}
        self.connected = False
        self.disconnected = False
        self.published = []
        self.local_participant = SimpleNamespace(publish_track=self._publish)
        self.__class__.instances.append(self)

    def on(self, event, handler):
        self.handlers[event] = handler

    async def connect(self, url, token):
        self.connected = True
        self.url = url
        self.token = token

    async def _publish(self, track):
        self.published.append(track)

    async def disconnect(self):
        self.disconnected = True


class FakeRtc:
    PlatformAudio = FakePlatformAudio
    LocalAudioTrack = FakeLocalAudioTrack
    Room = FakeRoom


@pytest.mark.asyncio
async def test_join_creates_default_room_and_session_file(fake_sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / ".voicemode"))
    FakeRoom.instances.clear()
    wait_hit = {"done": False}

    async def finish():
        wait_hit["done"] = True
        session = read_native_session()
        assert session is not None
        assert session["room_name"] == DEFAULT_NATIVE_ROOM
        assert session["kind"] == "native"

    room_name = await join_native_room(
        config=configured(),
        rtc_module=FakeRtc,
        wait=finish,
    )

    assert room_name == DEFAULT_NATIVE_ROOM
    assert wait_hit["done"] is True
    assert FakeRoom.instances[-1].connected is True
    assert FakeRoom.instances[-1].published
    assert FakeRoom.instances[-1].disconnected is True
    assert read_native_session() is None


def test_native_token_allows_hour_ttl(fake_sdk):
    client = LiveKitClient(configured())
    result = client.mint_native_token("voicemode-native")
    from tests.test_livekit_foundation import FakeAccessToken

    issued = FakeAccessToken.instances[-1]
    assert issued.ttl == MAX_NATIVE_TOKEN_TTL
    assert result.kind == ParticipantKind.NATIVE
    assert result.identity.startswith("voicemode-native-")
    with pytest.raises(LiveKitError) as caught:
        client.mint_native_token(
            "voicemode-native",
            ttl=timedelta(hours=1, seconds=1),
        )
    assert caught.value.code == "invalid_token_ttl"
