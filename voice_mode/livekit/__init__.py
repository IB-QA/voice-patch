"""Optional, isolated LiveKit foundation for VoiceMode."""

from .client import MAX_TOKEN_TTL, LiveKitClient, api_url
from .config import BrowserConfig, LiveKitConfig
from .errors import (
    LiveKitConfigurationError,
    LiveKitDependencyMissingError,
    LiveKitError,
    LiveKitRoomError,
)
from .models import (
    LiveKitConversationRequest,
    LiveKitConversationResult,
    ParticipantKind,
    ParticipantTokenRequest,
    ParticipantTokenResult,
    ResolveRoomRequest,
    ResolveRoomResult,
    Room,
)

__all__ = [
    "MAX_TOKEN_TTL",
    "BrowserConfig",
    "LiveKitClient",
    "LiveKitConfig",
    "LiveKitConfigurationError",
    "LiveKitConversationRequest",
    "LiveKitConversationResult",
    "LiveKitDependencyMissingError",
    "LiveKitError",
    "LiveKitRoomError",
    "ParticipantKind",
    "ParticipantTokenRequest",
    "ParticipantTokenResult",
    "ResolveRoomRequest",
    "ResolveRoomResult",
    "Room",
    "api_url",
]
