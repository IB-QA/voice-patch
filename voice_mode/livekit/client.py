"""Lazy, closeable abstraction over the optional LiveKit server API."""

import importlib
import secrets
from datetime import timedelta
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .config import LiveKitConfig
from .errors import (
    LiveKitDependencyMissingError,
    LiveKitError,
    LiveKitRoomError,
)
from .models import (
    ParticipantKind,
    ParticipantTokenRequest,
    ParticipantTokenResult,
    ResolveRoomRequest,
    ResolveRoomResult,
    Room,
)


MAX_TOKEN_TTL = timedelta(minutes=5)
MAX_NATIVE_TOKEN_TTL = timedelta(hours=1)


def api_url(url: str) -> str:
    """Translate a LiveKit websocket URL to its HTTP API equivalent."""

    parsed = urlsplit(url)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    return urlunsplit(parsed._replace(scheme=scheme))


def _load_livekit_api() -> ModuleType:
    try:
        return importlib.import_module("livekit.api")
    except ImportError:
        raise LiveKitDependencyMissingError() from None


class LiveKitClient:
    """Small phase-one client for rooms and participant token issuance."""

    def __init__(self, config: LiveKitConfig) -> None:
        api_key, api_secret = config.require_credentials()
        livekit_api = _load_livekit_api()
        self._config = config
        self._livekit_api = livekit_api
        self._closed = False
        try:
            self._api = livekit_api.LiveKitAPI(
                api_url(config.url),
                api_key=api_key,
                api_secret=api_secret,
            )
        except Exception:
            raise LiveKitError(
                "client_creation_failed",
                "Could not create the LiveKit API client.",
            ) from None

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(url={self._config.url!r}, "
            f"closed={self._closed!r})"
        )

    async def __aenter__(self) -> "LiveKitClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying SDK client exactly once."""

        if self._closed:
            return
        self._closed = True
        try:
            await self._api.aclose()
        except Exception:
            raise LiveKitError(
                "client_close_failed",
                "Could not close the LiveKit API client.",
            ) from None

    async def list_rooms(self) -> tuple[Room, ...]:
        """List rooms in stable name order."""

        self._ensure_open()
        try:
            response = await self._api.room.list_rooms(
                self._livekit_api.ListRoomsRequest(),
            )
        except Exception:
            raise LiveKitError(
                "room_list_failed",
                "Could not list LiveKit rooms.",
            ) from None
        rooms = (
            Room(
                name=room.name,
                participant_count=getattr(room, "num_participants", 0),
            )
            for room in response.rooms
        )
        return tuple(sorted(rooms, key=lambda room: room.name))

    async def create_room(self, room_name: str) -> Room:
        """Create one exact room through the public LiveKit room API."""

        self._ensure_open()
        if not room_name:
            raise LiveKitRoomError(
                "room_required",
                "A non-empty LiveKit room name is required.",
            )
        try:
            response = await self._api.room.create_room(
                self._livekit_api.CreateRoomRequest(name=room_name),
            )
        except Exception:
            raise LiveKitRoomError(
                "room_create_failed",
                "Could not create the LiveKit browser room.",
            ) from None
        return Room(
            name=response.name,
            participant_count=getattr(response, "num_participants", 0),
        )

    async def resolve_room(
        self,
        request: ResolveRoomRequest = ResolveRoomRequest(),
    ) -> ResolveRoomResult:
        """Resolve an exact or unambiguous prefix-eligible room."""

        rooms = await self.list_rooms()
        available_names = tuple(room.name for room in rooms)

        if request.room_name is not None:
            match = next(
                (room for room in rooms if room.name == request.room_name),
                None,
            )
            if match is None:
                raise LiveKitRoomError(
                    "room_not_found",
                    f"LiveKit room {request.room_name!r} was not found.",
                )
            return ResolveRoomResult(match, available_names)

        eligible = tuple(
            room
            for room in rooms
            if room.name.startswith(self._config.room_prefix)
        )
        if not eligible:
            raise LiveKitRoomError(
                "room_not_found",
                "No LiveKit rooms match the configured room prefix.",
            )
        if len(eligible) > 1:
            names = tuple(room.name for room in eligible)
            raise LiveKitRoomError(
                "room_required",
                "Multiple LiveKit rooms are available; specify an exact room "
                f"name. Available rooms: {', '.join(names)}.",
            )
        return ResolveRoomResult(eligible[0], available_names)

    def mint_participant_token(
        self,
        request: ParticipantTokenRequest,
    ) -> ParticipantTokenResult:
        """Mint a least-privilege, short-lived exact-room token."""

        self._ensure_open()
        if not request.room_name:
            raise LiveKitError(
                "room_required",
                "An exact LiveKit room name is required to mint a token.",
            )
        max_ttl = (
            MAX_NATIVE_TOKEN_TTL
            if request.kind == ParticipantKind.NATIVE
            else MAX_TOKEN_TTL
        )
        if request.ttl <= timedelta(0) or request.ttl > max_ttl:
            raise LiveKitError(
                "invalid_token_ttl",
                "LiveKit participant token TTL must be greater than zero and "
                "within the limit for this participant kind.",
            )

        identity = request.identity or (
            f"voicemode-{request.kind.value}-{secrets.token_urlsafe(18)}"
        )
        api_key, api_secret = self._config.require_credentials()
        try:
            token = (
                self._livekit_api.AccessToken(api_key, api_secret)
                .with_identity(identity)
                .with_ttl(request.ttl)
                .with_grants(
                    self._livekit_api.VideoGrants(
                        room_join=True,
                        room=request.room_name,
                        can_publish=request.can_publish,
                        can_subscribe=request.can_subscribe,
                    ),
                )
            )
            if request.display_name is not None:
                token = token.with_name(request.display_name)
            jwt = token.to_jwt()
        except Exception:
            raise LiveKitError(
                "token_issue_failed",
                "Could not mint the LiveKit participant token.",
            ) from None

        return ParticipantTokenResult(
            token=jwt,
            room_name=request.room_name,
            identity=identity,
            kind=request.kind,
            ttl=request.ttl,
        )

    def mint_browser_token(
        self,
        room_name: str,
        *,
        identity: str | None = None,
        display_name: str | None = None,
        ttl: timedelta = MAX_TOKEN_TTL,
    ) -> ParticipantTokenResult:
        return self.mint_participant_token(
            ParticipantTokenRequest(
                room_name=room_name,
                kind=ParticipantKind.BROWSER,
                identity=identity,
                display_name=display_name,
                ttl=ttl,
                can_publish=True,
                can_subscribe=True,
            ),
        )

    def mint_native_token(
        self,
        room_name: str,
        *,
        identity: str | None = None,
        display_name: str | None = None,
        ttl: timedelta = MAX_NATIVE_TOKEN_TTL,
    ) -> ParticipantTokenResult:
        return self.mint_participant_token(
            ParticipantTokenRequest(
                room_name=room_name,
                kind=ParticipantKind.NATIVE,
                identity=identity,
                display_name=display_name,
                ttl=ttl,
                can_publish=True,
                can_subscribe=True,
            ),
        )

    def mint_agent_token(
        self,
        room_name: str,
        *,
        identity: str | None = None,
        display_name: str | None = None,
        ttl: timedelta = MAX_TOKEN_TTL,
    ) -> ParticipantTokenResult:
        return self.mint_participant_token(
            ParticipantTokenRequest(
                room_name=room_name,
                kind=ParticipantKind.AGENT,
                identity=identity,
                display_name=display_name,
                ttl=ttl,
                can_publish=True,
                can_subscribe=True,
            ),
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise LiveKitError(
                "client_closed",
                "The LiveKit API client is closed; create a new client.",
            )
