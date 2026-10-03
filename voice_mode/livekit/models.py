"""Immutable request and result models for the optional LiveKit integration."""

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Mapping


class ParticipantKind(str, Enum):
    """Participant roles supported by the phase-one token issuer."""

    BROWSER = "browser"
    AGENT = "agent"
    NATIVE = "native"


@dataclass(frozen=True)
class Room:
    """The stable subset of LiveKit room metadata exposed to callers."""

    name: str
    participant_count: int = 0


@dataclass(frozen=True)
class ResolveRoomRequest:
    """Request for deterministic room selection."""

    room_name: str | None = None


@dataclass(frozen=True)
class ResolveRoomResult:
    """A deterministically selected room."""

    room: Room
    available_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParticipantTokenRequest:
    """Parameters for a short-lived, exact-room participant token."""

    room_name: str
    kind: ParticipantKind
    identity: str | None = None
    display_name: str | None = None
    ttl: timedelta = timedelta(minutes=5)
    can_publish: bool = True
    can_subscribe: bool = True


@dataclass(frozen=True)
class ParticipantTokenResult:
    """Issued token metadata. The token is hidden from representations."""

    token: str = field(repr=False)
    room_name: str
    identity: str
    kind: ParticipantKind
    ttl: timedelta


@dataclass(frozen=True)
class LiveKitConversationRequest:
    """One browser-room speech exchange."""

    message: str
    room_name: str | None = None
    wait_for_response: bool = True
    listen_duration_max: float = 120.0
    voice: str | None = None
    tts_model: str | None = None
    tts_provider: str | None = None
    vad_aggressiveness: int | None = None


@dataclass(frozen=True)
class LiveKitConversationResult:
    """Stable result returned by the LiveKit room adapter."""

    response_text: str | None
    room_name: str
    stt_provider: str
    tts_provider: str
    stt_model: str
    tts_model: str
    voice: str
    timings: Mapping[str, float] = field(default_factory=dict)
    interrupted: bool = False
    remaining_text: str | None = None
