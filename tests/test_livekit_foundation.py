"""Unit tests for the optional phase-one LiveKit foundation."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from voice_mode.livekit import (
    LiveKitClient,
    LiveKitConfig,
    LiveKitConfigurationError,
    LiveKitDependencyMissingError,
    LiveKitError,
    LiveKitRoomError,
    ParticipantKind,
    ParticipantTokenRequest,
    ResolveRoomRequest,
    api_url,
)
from voice_mode.livekit import client as client_module


ENV_NAMES = (
    "VOICEMODE_LIVEKIT_URL",
    "LIVEKIT_URL",
    "VOICEMODE_LIVEKIT_API_KEY",
    "LIVEKIT_API_KEY",
    "VOICEMODE_LIVEKIT_API_SECRET",
    "LIVEKIT_API_SECRET",
    "VOICEMODE_LIVEKIT_ROOM_PREFIX",
    "LIVEKIT_ROOM_PREFIX",
)


class FakeAccessToken:
    instances = []

    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.identity = None
        self.name = None
        self.ttl = None
        self.grants = None
        self.__class__.instances.append(self)

    def with_identity(self, identity):
        self.identity = identity
        return self

    def with_name(self, name):
        self.name = name
        return self

    def with_ttl(self, ttl):
        self.ttl = ttl
        return self

    def with_grants(self, grants):
        self.grants = grants
        return self

    def to_jwt(self):
        return "header.payload.signature"


class FakeVideoGrants:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeRoomService:
    def __init__(self, rooms):
        self._rooms = rooms

    async def list_rooms(self, request):
        return SimpleNamespace(rooms=self._rooms)

    async def create_room(self, request):
        return SimpleNamespace(name=request.name, num_participants=0)


class FakeLiveKitAPI:
    instances = []
    rooms = []

    def __init__(self, url, *, api_key, api_secret):
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret
        self.room = FakeRoomService(self.__class__.rooms)
        self.closed = False
        self.__class__.instances.append(self)

    async def aclose(self):
        self.closed = True


class FakeListRoomsRequest:
    pass


class FakeCreateRoomRequest:
    def __init__(self, *, name):
        self.name = name


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    FakeAccessToken.instances.clear()
    FakeLiveKitAPI.instances.clear()
    FakeLiveKitAPI.rooms = []


@pytest.fixture
def fake_sdk(monkeypatch):
    sdk = SimpleNamespace(
        AccessToken=FakeAccessToken,
        VideoGrants=FakeVideoGrants,
        LiveKitAPI=FakeLiveKitAPI,
        ListRoomsRequest=FakeListRoomsRequest,
        CreateRoomRequest=FakeCreateRoomRequest,
    )
    monkeypatch.setattr(client_module, "_load_livekit_api", lambda: sdk)
    return sdk


def configured():
    return LiveKitConfig(
        api_key="test-key",
        api_secret="super-secret-value",
        room_prefix="vm-",
    )


def test_config_defaults_and_voicemode_precedence(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://fallback.example")
    monkeypatch.setenv("VOICEMODE_LIVEKIT_URL", "wss://primary.example")
    monkeypatch.setenv("LIVEKIT_API_KEY", "fallback-key")
    monkeypatch.setenv("VOICEMODE_LIVEKIT_API_KEY", "primary-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "fallback-secret")
    monkeypatch.setenv("VOICEMODE_LIVEKIT_API_SECRET", "primary-secret")
    monkeypatch.setenv("LIVEKIT_ROOM_PREFIX", "fallback-")
    monkeypatch.setenv("VOICEMODE_LIVEKIT_ROOM_PREFIX", "primary-")

    config = LiveKitConfig.from_env()

    assert config.url == "wss://primary.example"
    assert config.api_key == "primary-key"
    assert config.api_secret == "primary-secret"
    assert config.room_prefix == "primary-"


def test_config_default_has_no_credentials():
    config = LiveKitConfig.from_env()

    assert config.url == "ws://127.0.0.1:7880"
    assert config.api_key is None
    assert config.api_secret is None


@pytest.mark.parametrize(
    "url",
    [
        "ftp://127.0.0.1:7880",
        "ws://livekit.example:7880",
        "http://192.168.1.20:7880",
        "ws://key:secret@127.0.0.1:7880",
        "ws://127.0.0.1:7880?password=secret",
    ],
)
def test_config_rejects_invalid_or_insecure_urls(url):
    with pytest.raises(LiveKitConfigurationError):
        LiveKitConfig(url=url)


@pytest.mark.parametrize(
    "url",
    [
        "ws://localhost:7880",
        "http://[::1]:7880",
        "wss://livekit.example",
        "https://livekit.example",
    ],
)
def test_config_accepts_loopback_insecure_and_remote_secure_urls(url):
    assert LiveKitConfig(url=url).url == url


def test_missing_credentials_are_typed_and_actionable():
    with pytest.raises(LiveKitConfigurationError) as caught:
        LiveKitConfig().require_credentials()

    assert caught.value.code == "credentials_missing"
    assert "VOICEMODE_LIVEKIT_API_KEY" in str(caught.value)


def test_missing_optional_dependency_is_actionable(monkeypatch):
    def missing(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(client_module.importlib, "import_module", missing)

    with pytest.raises(LiveKitDependencyMissingError) as caught:
        LiveKitClient(configured())

    assert caught.value.code == "dependency_missing"
    assert "voice-mode[livekit]" in str(caught.value)


def test_api_url_translation():
    assert api_url("ws://127.0.0.1:7880/path") == "http://127.0.0.1:7880/path"
    assert api_url("wss://livekit.example") == "https://livekit.example"
    assert api_url("https://livekit.example") == "https://livekit.example"


@pytest.mark.asyncio
async def test_room_resolution_zero_rooms(fake_sdk):
    client = LiveKitClient(configured())

    with pytest.raises(LiveKitRoomError) as caught:
        await client.resolve_room()

    assert caught.value.code == "room_not_found"
    await client.aclose()


@pytest.mark.asyncio
async def test_room_resolution_selects_only_prefix_eligible_room(fake_sdk):
    FakeLiveKitAPI.rooms = [
        SimpleNamespace(name="outside", num_participants=99),
        SimpleNamespace(name="vm-only", num_participants=2),
    ]
    client = LiveKitClient(configured())

    result = await client.resolve_room()

    assert result.room.name == "vm-only"
    assert result.room.participant_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_room_resolution_requires_name_for_multiple_rooms(fake_sdk):
    FakeLiveKitAPI.rooms = [
        SimpleNamespace(name="vm-z", num_participants=0),
        SimpleNamespace(name="vm-a", num_participants=3),
    ]
    client = LiveKitClient(configured())

    with pytest.raises(LiveKitRoomError) as caught:
        await client.resolve_room()

    assert caught.value.code == "room_required"
    assert "vm-a, vm-z" in str(caught.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_explicit_room_is_exact_and_may_be_outside_prefix(fake_sdk):
    FakeLiveKitAPI.rooms = [
        SimpleNamespace(name="outside", num_participants=1),
        SimpleNamespace(name="vm-room", num_participants=0),
    ]
    client = LiveKitClient(configured())

    result = await client.resolve_room(ResolveRoomRequest("outside"))

    assert result.room.name == "outside"
    with pytest.raises(LiveKitRoomError) as caught:
        await client.resolve_room(ResolveRoomRequest("out"))
    assert caught.value.code == "room_not_found"
    await client.aclose()


def test_token_uses_exact_room_grants_and_five_minute_ttl(fake_sdk):
    client = LiveKitClient(configured())

    result = client.mint_participant_token(
        ParticipantTokenRequest(
            room_name="vm-exact",
            kind=ParticipantKind.BROWSER,
            display_name="Browser",
        ),
    )

    issued = FakeAccessToken.instances[-1]
    assert issued.ttl == timedelta(minutes=5)
    assert issued.name == "Browser"
    assert issued.grants.room_join is True
    assert issued.grants.room == "vm-exact"
    assert issued.grants.can_publish is True
    assert issued.grants.can_subscribe is True
    assert result.room_name == "vm-exact"
    assert result.identity.startswith("voicemode-browser-")
    assert "header.payload.signature" not in repr(result)


@pytest.mark.asyncio
async def test_create_room_uses_public_request_and_stable_model(fake_sdk):
    client = LiveKitClient(configured())
    room = await client.create_room("vm-browser")
    assert room.name == "vm-browser"
    assert room.participant_count == 0
    await client.aclose()


def test_token_rejects_ttl_over_five_minutes(fake_sdk):
    client = LiveKitClient(configured())

    with pytest.raises(LiveKitError) as caught:
        client.mint_agent_token(
            "vm-room",
            ttl=timedelta(minutes=5, seconds=1),
        )

    assert caught.value.code == "invalid_token_ttl"


def test_secret_is_redacted_from_representations_and_errors(fake_sdk):
    config = configured()
    client = LiveKitClient(config)

    assert "super-secret-value" not in repr(config)
    assert "super-secret-value" not in repr(client)
    assert "super-secret-value" not in str(
        LiveKitError("example", "safe failure"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_inside", [False, True])
async def test_context_manager_closes_on_success_and_error(fake_sdk, raise_inside):
    with pytest.raises(RuntimeError) if raise_inside else _does_not_raise():
        async with LiveKitClient(configured()):
            if raise_inside:
                raise RuntimeError("operation failed")

    assert FakeLiveKitAPI.instances[-1].closed is True


class _does_not_raise:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback):
        return False
