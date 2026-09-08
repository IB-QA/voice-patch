"""Paths, configuration, and health helpers for managed LiveKit Server."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from voice_mode.utils.services.common import find_process_by_port, is_port_accessible


DEFAULT_LIVEKIT_PORT = 7880
DEFAULT_LIVEKIT_BROWSER_PORT = 7890
DEFAULT_RTC_PORT_START = 50000
DEFAULT_RTC_PORT_END = 50100
LIVEKIT_PROCESS_NAME = "livekit-server"


def voicemode_base_dir() -> Path:
    """Return the configured VoiceMode state directory."""

    return Path(
        os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    )


def livekit_service_dir() -> Path:
    return voicemode_base_dir() / "services" / "livekit"


def livekit_log_dir() -> Path:
    return voicemode_base_dir() / "logs" / "livekit"


def livekit_config_path() -> Path:
    return livekit_service_dir() / "livekit.yaml"


def livekit_metadata_path() -> Path:
    return livekit_service_dir() / "install.json"


def livekit_start_script_path() -> Path:
    return livekit_service_dir() / "bin" / "start-livekit-server.sh"


def livekit_browser_start_script_path() -> Path:
    return livekit_service_dir() / "bin" / "start-livekit-browser.sh"


def read_livekit_browser_port() -> int:
    try:
        port = int(
            os.environ.get(
                "VOICEMODE_LIVEKIT_BROWSER_PORT",
                DEFAULT_LIVEKIT_BROWSER_PORT,
            )
        )
        if 1 <= port <= 65535:
            return port
    except ValueError:
        pass
    return DEFAULT_LIVEKIT_BROWSER_PORT


@dataclass(frozen=True)
class LiveKitServiceMetadata:
    """Persisted facts needed to operate the installed server."""

    binary: Path
    version: str
    source: str


def read_livekit_metadata() -> LiveKitServiceMetadata | None:
    """Read installer metadata, returning ``None`` for absent/invalid data."""

    try:
        data = json.loads(livekit_metadata_path().read_text(encoding="utf-8"))
        binary = data.get("binary")
        version = data.get("version")
        source = data.get("source")
        if not all(isinstance(value, str) and value for value in (binary, version, source)):
            return None
        return LiveKitServiceMetadata(Path(binary), version, source)
    except (OSError, ValueError, TypeError):
        return None


def read_livekit_port(config_path: Path | None = None) -> int:
    """Read LiveKit's control-plane port from its YAML configuration."""

    path = config_path or livekit_config_path()
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        port = data.get("port", DEFAULT_LIVEKIT_PORT) if isinstance(data, dict) else None
        port = int(port)
        if 1 <= port <= 65535:
            return port
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        pass
    return DEFAULT_LIVEKIT_PORT


def find_livekit_process(port: int | None = None):
    """Return the expected LiveKit process listening on its configured port."""

    process = find_process_by_port(port or read_livekit_port())
    if process is None:
        return None
    try:
        name = process.name().lower()
        cmdline = " ".join(process.cmdline()).lower()
    except Exception:
        return None
    if LIVEKIT_PROCESS_NAME in name or LIVEKIT_PROCESS_NAME in cmdline:
        return process
    return None


def livekit_health() -> dict[str, Any]:
    """Return JSON-safe process and control-port health."""

    port = read_livekit_port()
    process = find_livekit_process(port)
    reachable = is_port_accessible(port)
    return {
        "healthy": process is not None and reachable,
        "port": port,
        "port_reachable": reachable,
        "process_matches": process is not None,
        "pid": process.pid if process is not None else None,
    }
