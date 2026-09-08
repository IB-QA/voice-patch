"""Environment configuration for the optional LiveKit integration."""

import ipaddress
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .errors import LiveKitConfigurationError


DEFAULT_LIVEKIT_URL = "ws://127.0.0.1:7880"
DEFAULT_ROOM_PREFIX = "voicemode-"
DEFAULT_BROWSER_HOST = "127.0.0.1"
DEFAULT_BROWSER_PORT = 7890
_ALLOWED_SCHEMES = frozenset({"ws", "wss", "http", "https"})


def _first_env(primary: str, fallback: str) -> str | None:
    value = os.environ.get(primary)
    if value is not None:
        return value
    return os.environ.get(fallback)


def _is_loopback(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _origin_for(host: str, port: int) -> str:
    url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{url_host}:{port}"


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise LiveKitConfigurationError(
            "invalid_url",
            "LiveKit URL must use ws, wss, http, or https and include a host.",
        )
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LiveKitConfigurationError(
            "invalid_url",
            "LiveKit URL must not contain credentials, a query, or a fragment.",
        )
    if parsed.scheme in {"ws", "http"} and not _is_loopback(parsed.hostname):
        raise LiveKitConfigurationError(
            "insecure_url",
            "Insecure LiveKit ws/http URLs are allowed only on loopback; use "
            "wss/https for remote hosts.",
        )


@dataclass(frozen=True)
class LiveKitConfig:
    """Validated LiveKit connection configuration."""

    url: str = DEFAULT_LIVEKIT_URL
    api_key: str | None = None
    api_secret: str | None = field(default=None, repr=False)
    room_prefix: str = DEFAULT_ROOM_PREFIX

    def __post_init__(self) -> None:
        _validate_url(self.url)
        if not self.room_prefix:
            raise LiveKitConfigurationError(
                "invalid_room_prefix",
                "LiveKit room prefix must not be empty.",
            )

    @classmethod
    def from_env(cls) -> "LiveKitConfig":
        """Load configuration with VoiceMode variables taking precedence."""

        return cls(
            url=_first_env("VOICEMODE_LIVEKIT_URL", "LIVEKIT_URL")
            or DEFAULT_LIVEKIT_URL,
            api_key=_first_env(
                "VOICEMODE_LIVEKIT_API_KEY",
                "LIVEKIT_API_KEY",
            ),
            api_secret=_first_env(
                "VOICEMODE_LIVEKIT_API_SECRET",
                "LIVEKIT_API_SECRET",
            ),
            room_prefix=_first_env(
                "VOICEMODE_LIVEKIT_ROOM_PREFIX",
                "LIVEKIT_ROOM_PREFIX",
            )
            or DEFAULT_ROOM_PREFIX,
        )

    def require_credentials(self) -> tuple[str, str]:
        """Return credentials or raise an actionable typed error."""

        if not self.api_key or not self.api_secret:
            raise LiveKitConfigurationError(
                "credentials_missing",
                "LiveKit API credentials are required; set "
                "VOICEMODE_LIVEKIT_API_KEY and VOICEMODE_LIVEKIT_API_SECRET.",
            )
        return self.api_key, self.api_secret


@dataclass(frozen=True)
class BrowserConfig:
    """Validated configuration for the loopback-only browser gateway."""

    host: str = DEFAULT_BROWSER_HOST
    port: int = DEFAULT_BROWSER_PORT
    token: str | None = field(default=None, repr=False)
    origin: str | None = None

    def __post_init__(self) -> None:
        if not _is_loopback(self.host):
            raise LiveKitConfigurationError(
                "browser_non_loopback",
                "The LiveKit browser gateway is loopback-only in this release.",
            )
        if not 1 <= self.port <= 65535:
            raise LiveKitConfigurationError(
                "browser_invalid_port",
                "The LiveKit browser gateway port must be between 1 and 65535.",
            )
        expected_origin = _origin_for(self.host, self.port)
        if self.origin is None:
            object.__setattr__(self, "origin", expected_origin)
        elif self.origin != expected_origin:
            raise LiveKitConfigurationError(
                "browser_invalid_origin",
                f"Browser origin must exactly match {expected_origin}.",
            )

    @classmethod
    def from_env(
        cls,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> "BrowserConfig":
        """Load browser settings, with explicit CLI values taking precedence."""

        env_host = os.environ.get("VOICEMODE_LIVEKIT_BROWSER_HOST")
        env_port = os.environ.get("VOICEMODE_LIVEKIT_BROWSER_PORT")
        selected_port = port
        if selected_port is None:
            try:
                selected_port = int(env_port) if env_port else DEFAULT_BROWSER_PORT
            except ValueError:
                raise LiveKitConfigurationError(
                    "browser_invalid_port",
                    "VOICEMODE_LIVEKIT_BROWSER_PORT must be an integer.",
                ) from None
        selected_host = host or env_host or DEFAULT_BROWSER_HOST
        configured_origin = os.environ.get("VOICEMODE_LIVEKIT_BROWSER_ORIGIN")
        default_origin = _origin_for(selected_host, selected_port)
        return cls(
            host=selected_host,
            port=selected_port,
            token=os.environ.get("VOICEMODE_LIVEKIT_BROWSER_TOKEN"),
            origin=configured_origin or default_origin,
        )

    def require_token(self) -> str:
        """Return the gateway bearer or fail with actionable guidance."""

        if not self.token:
            raise LiveKitConfigurationError(
                "browser_token_missing",
                "LiveKit browser access requires "
                "VOICEMODE_LIVEKIT_BROWSER_TOKEN; run "
                "`voicemode service install livekit` to generate it.",
            )
        return self.token

    @property
    def url(self) -> str:
        return self.origin or _origin_for(self.host, self.port)
