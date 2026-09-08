"""Real LiveKit loopback integration gate.

Run explicitly with:

    VOICEMODE_RUN_LIVEKIT_INTEGRATION=1 \
      uv run --extra livekit --extra test pytest \
      tests/integration/test_livekit_real.py -v -s --no-cov

The test starts an ephemeral loopback-only LiveKit Server, uses the configured
real TTS/STT services, and never reads or writes persistent LiveKit state.
"""

import asyncio
import importlib.util
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from voice_mode import config as voice_config
from voice_mode.livekit.client import LiveKitClient
from voice_mode.livekit.config import LiveKitConfig
from voice_mode.livekit.models import LiveKitConversationRequest
from voice_mode.livekit.transport import converse_livekit

try:
    from livekit import api, rtc
except ImportError:
    api = None
    rtc = None

_LIVEKIT_OPTIONALS_AVAILABLE = all(
    importlib.util.find_spec(module) is not None
    for module in (
        "livekit.api",
        "livekit.rtc",
        "livekit.agents",
        "livekit.plugins.openai",
        "livekit.plugins.silero",
    )
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("VOICEMODE_RUN_LIVEKIT_INTEGRATION") != "1",
        reason="set VOICEMODE_RUN_LIVEKIT_INTEGRATION=1 to run real LiveKit tests",
    ),
    pytest.mark.skipif(
        shutil.which("livekit-server") is None,
        reason="livekit-server is not installed",
    ),
    pytest.mark.skipif(
        api is None or rtc is None or not _LIVEKIT_OPTIONALS_AVAILABLE,
        reason="LiveKit optional SDKs are not installed",
    ),
]

_PHRASE = "violet harbor seven"
_SAMPLE_RATE = 24_000
_CHANNELS = 1
_FRAME_DURATION = 0.02
_SAMPLES_PER_FRAME = int(_SAMPLE_RATE * _FRAME_DURATION)


@dataclass
class _Server:
    config: LiveKitConfig
    process: subprocess.Popen[bytes]
    version: str
    log_path: Path


def _unused_port(*, sock_type: int = socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, sock_type) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 15
    last_error = "server did not answer"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"livekit-server exited with {process.returncode}")
        try:
            response = httpx.get(url, timeout=0.5)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as error:
            last_error = str(error)
        time.sleep(0.1)
    raise RuntimeError(f"livekit-server health timed out: {last_error}")


def _require_speech_services() -> None:
    endpoints = (
        ("TTS", voice_config.TTS_BASE_URLS[0]),
        ("STT", voice_config.STT_BASE_URLS[0]),
    )
    for kind, base_url in endpoints:
        health_url = f"{base_url.removesuffix('/v1')}/health"
        try:
            response = httpx.get(health_url, timeout=3)
        except httpx.HTTPError as error:
            pytest.skip(f"{kind} service unavailable at {health_url}: {error}")
        if response.status_code != 200:
            pytest.skip(
                f"{kind} service unhealthy at {health_url}: "
                f"HTTP {response.status_code}"
            )


@pytest.fixture
def livekit_server() -> Any:
    _require_speech_services()
    binary = shutil.which("livekit-server")
    assert binary is not None
    http_port = _unused_port()
    udp_port = _unused_port(sock_type=socket.SOCK_DGRAM)
    api_key = f"lk_{secrets.token_urlsafe(12)}"
    api_secret = secrets.token_urlsafe(32)
    version_result = subprocess.run(
        [binary, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    version = (version_result.stdout or version_result.stderr).strip()

    with tempfile.TemporaryDirectory(prefix="voicemode-livekit-real-") as temp_dir:
        temp_path = Path(temp_dir)
        config_path = temp_path / "livekit.yaml"
        log_path = temp_path / "livekit.log"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "port": http_port,
                    "bind_addresses": ["127.0.0.1"],
                    "rtc": {
                        "port_range_start": udp_port,
                        "port_range_end": udp_port,
                        "use_external_ip": False,
                    },
                    "keys": {api_key: api_secret},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [binary, "--config", str(config_path)],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            server = _Server(
                config=LiveKitConfig(
                    url=f"ws://127.0.0.1:{http_port}",
                    api_key=api_key,
                    api_secret=api_secret,
                    room_prefix="real-",
                ),
                process=process,
                version=version,
                log_path=log_path,
            )
            try:
                _wait_for_http(f"http://127.0.0.1:{http_port}", process)
                yield server
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                print(
                    "LIVEKIT_REAL_SERVER_CLEANUP "
                    f"returncode={process.returncode} terminated={process.poll() is not None}"
                )


def _speech_pcm() -> bytes:
    response = httpx.post(
        f"{voice_config.TTS_BASE_URLS[0].rstrip('/')}/audio/speech",
        json={
            "model": voice_config.TTS_MODELS[0],
            "voice": voice_config.TTS_VOICES[0],
            "input": _PHRASE,
            "response_format": "pcm",
        },
        headers={"Authorization": "Bearer dummy-key-for-local"},
        timeout=30,
    )
    response.raise_for_status()
    assert response.content
    silence = bytes(_SAMPLE_RATE * 2)
    return silence + response.content + silence


async def _publish_microphone(room: Any, pcm: bytes) -> None:
    source = rtc.AudioSource(_SAMPLE_RATE, _CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("synthetic-microphone", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, options)
    frame_bytes = _SAMPLES_PER_FRAME * 2
    try:
        for offset in range(0, len(pcm), frame_bytes):
            chunk = pcm[offset : offset + frame_bytes]
            if len(chunk) < frame_bytes:
                chunk += bytes(frame_bytes - len(chunk))
            frame = rtc.AudioFrame(
                chunk,
                sample_rate=_SAMPLE_RATE,
                num_channels=_CHANNELS,
                samples_per_channel=_SAMPLES_PER_FRAME,
            )
            await source.capture_frame(frame)
            await asyncio.sleep(_FRAME_DURATION)
        await source.wait_for_playout()
    finally:
        await source.aclose()


async def _participant_count(server: _Server, room_name: str) -> int:
    client = api.LiveKitAPI(
        server.config.url.replace("ws://", "http://"),
        api_key=server.config.api_key,
        api_secret=server.config.api_secret,
    )
    try:
        response = await client.room.list_participants(
            api.ListParticipantsRequest(room=room_name)
        )
        return len(response.participants)
    finally:
        await client.aclose()


async def _wait_for_participant_count(
    server: _Server,
    room_name: str,
    expected: int,
    *,
    timeout: float = 10,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    actual = -1
    while asyncio.get_running_loop().time() < deadline:
        actual = await _participant_count(server, room_name)
        if actual == expected:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"expected {expected} participants in {room_name!r}, found {actual}"
    )


@pytest.mark.timeout(90)
async def test_real_room_tts_and_stt_loopback(livekit_server: _Server) -> None:
    room_name = f"real-{secrets.token_urlsafe(8)}"
    setup_client = LiveKitClient(livekit_server.config)
    browser_room = rtc.Room()
    stream_tasks: set[asyncio.Task[None]] = set()
    agent_audio_seen = asyncio.Event()
    audio_stats = {"frames": 0, "samples": 0, "sample_rate": 0}

    async def consume_agent_audio(track: Any) -> None:
        stream = rtc.AudioStream(track)
        try:
            async for event in stream:
                frame = event.frame
                audio_stats["frames"] += 1
                audio_stats["samples"] += frame.samples_per_channel
                audio_stats["sample_rate"] = frame.sample_rate
                if audio_stats["samples"] >= frame.sample_rate // 2:
                    agent_audio_seen.set()
        finally:
            await stream.aclose()

    def on_track_subscribed(
        track: Any,
        publication: Any,
        participant: Any,
    ) -> None:
        del publication
        if (
            track.kind == rtc.TrackKind.KIND_AUDIO
            and participant.identity.startswith("voicemode-agent-")
        ):
            task = asyncio.create_task(consume_agent_audio(track))
            stream_tasks.add(task)
            task.add_done_callback(stream_tasks.discard)

    browser_room.on("track_subscribed", on_track_subscribed)

    try:
        await setup_client.create_room(room_name)
        browser_token = setup_client.mint_browser_token(
            room_name,
            identity=f"synthetic-browser-{secrets.token_urlsafe(6)}",
        )
        await browser_room.connect(livekit_server.config.url, browser_token.token)
        microphone_pcm = await asyncio.to_thread(_speech_pcm)
        conversation_task = asyncio.create_task(
            converse_livekit(
                LiveKitConversationRequest(
                    message="Loopback check.",
                    room_name=room_name,
                    listen_duration_max=30,
                    vad_aggressiveness=1,
                ),
                config=livekit_server.config,
            )
        )
        await asyncio.wait_for(agent_audio_seen.wait(), timeout=30)
        # Do not barge into the agent's prompt. AgentSession suppresses user
        # input while its own speech is playing, so overlapping here would test
        # interruption behavior and intentionally clip the beginning.
        await asyncio.sleep(2.5)
        await _publish_microphone(browser_room, microphone_pcm)
        result = await asyncio.wait_for(conversation_task, timeout=45)

        transcript = result.response_text or ""
        normalized = {
            word.strip(".,!?;:\"'").lower() for word in transcript.split()
        }
        expected = set(_PHRASE.split())
        assert len(normalized & expected) >= 2, transcript
        duration = audio_stats["samples"] / audio_stats["sample_rate"]
        assert audio_stats["frames"] > 0
        assert duration >= 0.5
        assert await _participant_count(livekit_server, room_name) == 1
        print(
            "LIVEKIT_REAL_EVIDENCE "
            f"server={livekit_server.version!r} "
            f"audio_frames={audio_stats['frames']} "
            f"audio_duration={duration:.3f}s "
            f"transcript={transcript!r} "
            "agent_cleanup=True"
        )
    finally:
        await browser_room.disconnect()
        await setup_client.aclose()
        if "conversation_task" in locals() and not conversation_task.done():
            conversation_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await conversation_task
        if stream_tasks:
            await asyncio.gather(*stream_tasks, return_exceptions=True)

    assert browser_room.connection_state == rtc.ConnectionState.CONN_DISCONNECTED
    assert await _participant_count(livekit_server, room_name) == 0
    print("LIVEKIT_REAL_ROOM_CLEANUP participants=0 browser_disconnected=True")


@pytest.mark.timeout(60)
async def test_real_cancellation_cleans_agent_room_session(
    livekit_server: _Server,
) -> None:
    room_name = f"real-cancel-{secrets.token_urlsafe(8)}"
    setup_client = LiveKitClient(livekit_server.config)
    browser_room = rtc.Room()
    conversation_task: asyncio.Task[Any] | None = None

    try:
        await setup_client.create_room(room_name)
        token = setup_client.mint_browser_token(
            room_name,
            identity=f"synthetic-cancel-{secrets.token_urlsafe(6)}",
        )
        await browser_room.connect(livekit_server.config.url, token.token)
        conversation_task = asyncio.create_task(
            converse_livekit(
                LiveKitConversationRequest(
                    message="Cancellation check.",
                    room_name=room_name,
                    listen_duration_max=30,
                ),
                config=livekit_server.config,
            )
        )
        await _wait_for_participant_count(livekit_server, room_name, 2)
        # The short prompt has completed by this point and the exchange is
        # waiting for browser speech, which is intentionally never published.
        await asyncio.sleep(3)
        assert not conversation_task.done()
        conversation_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await conversation_task
        await _wait_for_participant_count(livekit_server, room_name, 1)
        print("LIVEKIT_REAL_CANCELLATION agent_cleanup=True participants=1")
    finally:
        if conversation_task is not None and not conversation_task.done():
            conversation_task.cancel()
            await asyncio.gather(conversation_task, return_exceptions=True)
        await browser_room.disconnect()
        await setup_client.aclose()

    await _wait_for_participant_count(livekit_server, room_name, 0)
    print("LIVEKIT_REAL_CANCEL_ROOM_CLEANUP participants=0")
