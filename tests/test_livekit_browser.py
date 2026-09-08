"""Security and packaging tests for the local LiveKit browser gateway."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli
from voice_mode.livekit import BrowserConfig, LiveKitConfig
from voice_mode.livekit import browser_app


class FakeBrowserClient:
    def __init__(self, config):
        self.config = config

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def create_room(self, room_name):
        return SimpleNamespace(name=room_name)

    def mint_browser_token(self, room_name, *, identity, display_name):
        return SimpleNamespace(token="participant.jwt", identity=identity)


@pytest.fixture
async def gateway(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html><title>VoiceMode</title>")
    monkeypatch.setattr(browser_app, "LiveKitClient", FakeBrowserClient)
    app = browser_app.create_app(
        BrowserConfig(token="browser-secret"),
        LiveKitConfig(api_key="key", api_secret="secret"),
        frontend_root=frontend,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


def session_headers(token="browser-secret", **overrides):
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "http://127.0.0.1:7890",
        "Host": "127.0.0.1:7890",
    }
    headers.update(overrides)
    return headers


@pytest.mark.asyncio
async def test_session_is_post_only_and_rejects_query(gateway):
    response = await gateway.get("/api/session")
    assert response.status == 405
    response = await gateway.post("/api/session?token=browser-secret")
    assert response.status == 400


@pytest.mark.asyncio
async def test_session_requires_exact_host_origin_and_bearer(gateway):
    response = await gateway.post(
        "/api/session",
        headers=session_headers(Origin="http://localhost:7890"),
    )
    assert response.status == 403
    response = await gateway.post(
        "/api/session",
        headers=session_headers(Host="localhost:7890"),
    )
    assert response.status == 400
    response = await gateway.post(
        "/api/session",
        headers=session_headers("wrong"),
    )
    assert response.status == 401
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_failed_auth_is_rate_limited(gateway):
    for _ in range(browser_app.AUTH_FAILURE_LIMIT):
        response = await gateway.post(
            "/api/session",
            headers=session_headers("wrong"),
        )
        assert response.status == 401
    response = await gateway.post(
        "/api/session",
        headers=session_headers("wrong"),
    )
    assert response.status == 429


@pytest.mark.asyncio
async def test_session_response_is_private_random_and_redacted(gateway):
    response = await gateway.post("/api/session", headers=session_headers())
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = await response.json()
    assert set(payload) == {
        "serverUrl",
        "roomName",
        "participantName",
        "participantToken",
    }
    serialized = str(payload)
    assert "browser-secret" not in serialized
    assert "secret" not in serialized
    assert "key" not in serialized
    assert payload["roomName"].startswith("voicemode-browser-")
    assert payload["participantName"].startswith("voicemode-browser-")


@pytest.mark.asyncio
async def test_security_headers_and_static_path_safety(gateway):
    response = await gateway.get("/")
    assert response.status == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    response = await gateway.get("/%2e%2e/pyproject.toml")
    assert response.status == 404


def test_browser_config_precedence_and_validation(monkeypatch):
    monkeypatch.setenv("VOICEMODE_LIVEKIT_BROWSER_HOST", "localhost")
    monkeypatch.setenv("VOICEMODE_LIVEKIT_BROWSER_PORT", "7001")
    monkeypatch.setenv("VOICEMODE_LIVEKIT_BROWSER_TOKEN", "configured")
    config = BrowserConfig.from_env(host="127.0.0.1", port=7002)
    assert config.host == "127.0.0.1"
    assert config.port == 7002
    assert config.token == "configured"
    assert config.origin == "http://127.0.0.1:7002"
    with pytest.raises(Exception, match="loopback-only"):
        BrowserConfig(host="0.0.0.0", token="configured")


def test_browser_open_uses_fragment_not_query(monkeypatch):
    opened = []
    monkeypatch.setenv("VOICEMODE_LIVEKIT_BROWSER_TOKEN", "a/b+c")
    monkeypatch.setattr(
        "voice_mode.cli_commands.livekit.webbrowser.open",
        lambda url: not opened.append(url),
    )
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["livekit", "browser", "open"],
    )
    assert result.exit_code == 0
    assert opened == ["http://127.0.0.1:7890/#token=a%2Fb%2Bc"]
    assert "?token=" not in opened[0]
    assert "a/b+c" not in result.output


def test_frontend_source_clears_fragment_and_gates_microphone():
    source = (
        Path(__file__).parents[1] / "web" / "livekit" / "src" / "main.ts"
    ).read_text()
    assert "history.replaceState" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.cookie" not in source
    assert 'microphoneButton.addEventListener("click"' in source
    assert "setMicrophoneEnabled(true)" in source
    assert 'window.addEventListener("pagehide", disconnect)' in source
    assert "autoSubscribe: true" in source
