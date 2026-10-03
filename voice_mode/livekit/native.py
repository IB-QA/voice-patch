"""Native LiveKit human participant: local mic in, room audio out. No browser."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, Callable

from voice_mode.utils.services.livekit_helpers import livekit_native_session_path

from .client import LiveKitClient
from .config import LiveKitConfig
from .errors import LiveKitDependencyMissingError, LiveKitRoomError
from .models import ResolveRoomRequest

logger = logging.getLogger("voicemode")

DEFAULT_NATIVE_ROOM = "voicemode-native"


def _load_rtc() -> ModuleType:
    try:
        return importlib.import_module("livekit.rtc")
    except ImportError:
        raise LiveKitDependencyMissingError() from None


def read_native_session() -> dict[str, Any] | None:
    path = livekit_native_session_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not payload.get("room_name"):
        return None
    return payload


def _write_native_session(room_name: str, identity: str) -> None:
    path = livekit_native_session_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "room_name": room_name,
        "identity": identity,
        "kind": "native",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _clear_native_session() -> None:
    path = livekit_native_session_path()
    try:
        path.unlink()
    except OSError:
        pass


async def _ensure_room(client: LiveKitClient, room_name: str | None) -> str:
    name = room_name or DEFAULT_NATIVE_ROOM
    try:
        resolved = await client.resolve_room(ResolveRoomRequest(room_name=name))
        return resolved.room.name
    except LiveKitRoomError as exc:
        if getattr(exc, "code", None) != "room_not_found":
            raise
        created = await client.create_room(name)
        return created.name


async def join_native_room(
    room_name: str | None = None,
    *,
    config: LiveKitConfig | None = None,
    rtc_module: ModuleType | None = None,
    wait: Callable[[], Any] | None = None,
) -> str:
    """Join as the local human: publish microphone, play subscribed audio."""

    rtc = rtc_module or _load_rtc()
    livekit_config = config or LiveKitConfig.from_env()
    async with LiveKitClient(livekit_config) as client:
        name = await _ensure_room(client, room_name)
        issued = client.mint_native_token(name, display_name="VoiceMode native")

    platform_audio = rtc.PlatformAudio()
    source = platform_audio.create_audio_source()
    room = rtc.Room()
    disconnected = asyncio.Event()

    def _on_disconnected(*_args: object, **_kwargs: object) -> None:
        disconnected.set()

    room.on("disconnected", _on_disconnected)
    try:
        await room.connect(livekit_config.url, issued.token)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        await room.local_participant.publish_track(track)
        _write_native_session(name, issued.identity)
        logger.info("Native LiveKit participant joined room %s", name)
        if wait is not None:
            await wait()
        else:
            await disconnected.wait()
    finally:
        _clear_native_session()
        try:
            source.close()
        except Exception:
            logger.debug("Native audio source close failed", exc_info=True)
        try:
            platform_audio.close()
        except Exception:
            logger.debug("Native platform audio close failed", exc_info=True)
        try:
            await room.disconnect()
        except Exception:
            logger.debug("Native room disconnect failed", exc_info=True)
    return name
