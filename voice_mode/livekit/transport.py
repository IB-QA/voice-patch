"""LiveKit room transport for one VoiceMode conversation exchange.

The optional LiveKit SDK imports stay behind :func:`_load_livekit_modules` so
the base installation and local transport do not require LiveKit.
"""

import asyncio
import importlib
import time
from dataclasses import dataclass
from types import ModuleType
from urllib.parse import urlsplit, urlunsplit

from voice_mode import config as voice_config
from voice_mode.provider_discovery import detect_provider_type, is_local_provider

from .client import LiveKitClient
from .config import LiveKitConfig
from .errors import LiveKitDependencyMissingError, LiveKitError
from .models import (
    LiveKitConversationRequest,
    LiveKitConversationResult,
    ResolveRoomRequest,
)


@dataclass(frozen=True)
class _LiveKitModules:
    rtc: ModuleType
    agents: ModuleType
    openai: ModuleType
    silero: ModuleType


def _load_livekit_modules() -> _LiveKitModules:
    """Load all optional room/agent modules as one actionable dependency."""

    try:
        return _LiveKitModules(
            rtc=importlib.import_module("livekit.rtc"),
            agents=importlib.import_module("livekit.agents"),
            openai=importlib.import_module("livekit.plugins.openai"),
            silero=importlib.import_module("livekit.plugins.silero"),
        )
    except ImportError:
        raise LiveKitDependencyMissingError() from None


def _rtc_url(url: str) -> str:
    parsed = urlsplit(url)
    scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme, parsed.scheme)
    return urlunsplit(parsed._replace(scheme=scheme))


def _provider_api_key(base_url: str) -> str:
    if is_local_provider(base_url):
        return voice_config.OPENAI_API_KEY or "dummy-key-for-local"
    if not voice_config.OPENAI_API_KEY:
        raise LiveKitError(
            "openai_api_key_missing",
            "The configured cloud speech endpoint requires OPENAI_API_KEY.",
        )
    return voice_config.OPENAI_API_KEY


def _configured_endpoint(kind: str) -> str:
    endpoints = (
        voice_config.STT_BASE_URLS
        if kind == "stt"
        else voice_config.TTS_BASE_URLS
    )
    if not endpoints:
        raise LiveKitError(
            f"{kind}_endpoint_missing",
            f"No {kind.upper()} endpoint is configured for LiveKit transport.",
        )
    return endpoints[0]


def _vad_threshold(aggressiveness: int | None) -> float:
    """Map VoiceMode's 0..3 WebRTC scale to Silero's speech threshold."""

    level = (
        voice_config.VAD_AGGRESSIVENESS
        if aggressiveness is None
        else aggressiveness
    )
    return (0.35, 0.45, 0.55, 0.65)[level]


async def converse_livekit(
    request: LiveKitConversationRequest,
    *,
    config: LiveKitConfig | None = None,
) -> LiveKitConversationResult:
    """Speak in one exact room and optionally return its first final transcript."""

    if request.listen_duration_max <= 0:
        raise LiveKitError(
            "invalid_listen_duration",
            "LiveKit listen_duration_max must be positive.",
        )
    if request.vad_aggressiveness is not None and not (
        0 <= request.vad_aggressiveness <= 3
    ):
        raise LiveKitError(
            "invalid_vad_aggressiveness",
            "LiveKit vad_aggressiveness must be between 0 and 3.",
        )

    modules = _load_livekit_modules()
    livekit_config = config or LiveKitConfig.from_env()
    client = LiveKitClient(livekit_config)
    room = None
    session = None
    started_at = time.perf_counter()
    timings: dict[str, float] = {}

    try:
        resolved = await client.resolve_room(
            ResolveRoomRequest(room_name=request.room_name)
        )
        room_name = resolved.room.name
        token = client.mint_agent_token(room_name)

        stt_url = _configured_endpoint("stt")
        tts_url = _configured_endpoint("tts")
        stt_model = voice_config.STT_MODEL
        tts_model = request.tts_model or (
            voice_config.TTS_MODELS[0]
            if voice_config.TTS_MODELS
            else voice_config.TTS_MODEL_DEFAULT
        )
        voice = request.voice or (
            voice_config.TTS_VOICES[0] if voice_config.TTS_VOICES else "alloy"
        )
        stt_provider = detect_provider_type(stt_url)
        tts_provider = request.tts_provider or detect_provider_type(tts_url)

        stt = modules.openai.STT(
            model=stt_model,
            base_url=stt_url,
            api_key=_provider_api_key(stt_url),
        )
        tts = modules.openai.TTS(
            model=tts_model,
            voice=voice,
            base_url=tts_url,
            api_key=_provider_api_key(tts_url),
            response_format="pcm",
        )
        vad = modules.silero.VAD.load(
            activation_threshold=_vad_threshold(request.vad_aggressiveness)
        )
        session = modules.agents.AgentSession(
            stt=stt,
            vad=vad,
            llm=None,
            tts=tts,
            transcription_timeout=request.listen_duration_max,
        )
        agent = modules.agents.Agent(
            instructions=(
                "Relay VoiceMode speech and transcribe the room participant. "
                "Do not generate an autonomous response."
            )
        )
        room = modules.rtc.Room()

        loop = asyncio.get_running_loop()
        transcript_future: asyncio.Future[str] = loop.create_future()
        failure_future: asyncio.Future[LiveKitError] = loop.create_future()

        def on_transcript(event: object) -> None:
            transcript = str(getattr(event, "transcript", "")).strip()
            if (
                getattr(event, "is_final", False)
                and transcript
                and not transcript_future.done()
            ):
                transcript_future.set_result(transcript)

        def on_session_error(event: object) -> None:
            if not failure_future.done():
                failure_future.set_result(
                    LiveKitError(
                        "session_error",
                        "The LiveKit speech session reported an error.",
                    )
                )

        def on_session_close(event: object) -> None:
            if request.wait_for_response and not failure_future.done():
                failure_future.set_result(
                    LiveKitError(
                        "session_closed",
                        "The LiveKit speech session closed before a response arrived.",
                    )
                )

        def on_room_disconnected(*args: object) -> None:
            if request.wait_for_response and not failure_future.done():
                failure_future.set_result(
                    LiveKitError(
                        "room_disconnected",
                        "The LiveKit room disconnected before a response arrived.",
                    )
                )

        session.on("user_input_transcribed", on_transcript)
        session.on("error", on_session_error)
        session.on("close", on_session_close)
        room.on("disconnected", on_room_disconnected)

        connect_started = time.perf_counter()
        try:
            await room.connect(
                _rtc_url(livekit_config.url),
                token.token,
                options=modules.rtc.RoomOptions(),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            raise LiveKitError(
                "room_connect_failed",
                f"Could not connect to LiveKit room {room_name!r}.",
            ) from None
        timings["connect"] = time.perf_counter() - connect_started

        try:
            await session.start(agent, room=room)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise LiveKitError(
                "session_start_failed",
                "Could not start the LiveKit speech session.",
            ) from None

        speak_started = time.perf_counter()
        try:
            handle = session.say(request.message)
            await handle.wait_for_playout()
        except asyncio.CancelledError:
            raise
        except Exception:
            raise LiveKitError(
                "playout_failed",
                "Could not publish VoiceMode speech to the LiveKit room.",
            ) from None
        timings["playout"] = time.perf_counter() - speak_started

        response_text = None
        if request.wait_for_response:
            listen_started = time.perf_counter()
            transcript_task = asyncio.ensure_future(transcript_future)
            failure_task = asyncio.ensure_future(failure_future)
            done, pending = await asyncio.wait(
                {transcript_task, failure_task},
                timeout=request.listen_duration_max,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if transcript_task in done:
                response_text = transcript_task.result()
            elif failure_task in done:
                raise failure_task.result()
            timings["listen"] = time.perf_counter() - listen_started

        timings["total"] = time.perf_counter() - started_at
        return LiveKitConversationResult(
            response_text=response_text,
            room_name=room_name,
            stt_provider=stt_provider,
            tts_provider=tts_provider,
            stt_model=stt_model,
            tts_model=tts_model,
            voice=voice,
            timings=timings,
        )
    except asyncio.CancelledError:
        raise
    except LiveKitError:
        raise
    except Exception:
        raise LiveKitError(
            "session_failed",
            "The LiveKit room conversation failed.",
        ) from None
    finally:
        try:
            if session is not None:
                try:
                    await session.aclose()
                except Exception:
                    pass
        finally:
            try:
                if room is not None:
                    try:
                        await room.disconnect()
                    except Exception:
                        pass
            finally:
                try:
                    await client.aclose()
                except Exception:
                    pass
