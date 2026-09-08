"""Uninstaller for the managed LiveKit SFU service."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from voice_mode.server import mcp
from voice_mode.utils.services.livekit_helpers import (
    find_livekit_process,
    livekit_log_dir,
    livekit_service_dir,
    voicemode_base_dir,
)


ENV_KEYS = {
    "VOICEMODE_LIVEKIT_URL",
    "VOICEMODE_LIVEKIT_API_KEY",
    "VOICEMODE_LIVEKIT_API_SECRET",
    "VOICEMODE_LIVEKIT_BROWSER_TOKEN",
    "VOICEMODE_LIVEKIT_BROWSER_HOST",
    "VOICEMODE_LIVEKIT_BROWSER_PORT",
    "VOICEMODE_LIVEKIT_BROWSER_ORIGIN",
}


def _remove_env_entries(path: Path) -> None:
    if not path.exists():
        return
    retained = []
    for line in path.read_text(encoding="utf-8").splitlines():
        key = line.strip().split("=", 1)[0].strip() if "=" in line else ""
        if key not in ENV_KEYS:
            retained.append(line)
    content = "\n".join(retained).rstrip()
    if content:
        content += "\n"
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _service_paths() -> tuple[Path, Path]:
    if platform.system() == "Darwin":
        root = Path.home() / "Library" / "LaunchAgents"
        return (
            root / "com.voicemode.livekit.plist",
            root / "com.voicemode.livekit-web.plist",
        )
    root = Path.home() / ".config" / "systemd" / "user"
    return (
        root / "voicemode-livekit.service",
        root / "voicemode-livekit-web.service",
    )


@mcp.tool()
async def livekit_uninstall(remove_all_data: bool = False) -> dict[str, Any]:
    """Stop LiveKit and remove its service, binaries, config, and credentials."""

    removed_items: list[str] = []
    errors: list[str] = []

    process = find_livekit_process()
    if process is not None:
        try:
            process.terminate()
            process.wait(timeout=10)
            removed_items.append(f"Stopped LiveKit (PID {process.pid})")
        except Exception as exc:
            errors.append(f"Failed to stop LiveKit: {exc}")

    for service_path in _service_paths():
        if not service_path.exists():
            continue
        try:
            if platform.system() == "Darwin":
                subprocess.run(
                    ["launchctl", "unload", str(service_path)],
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["systemctl", "--user", "disable", "--now", service_path.name],
                    capture_output=True,
                )
            service_path.unlink()
            if platform.system() == "Linux":
                subprocess.run(
                    ["systemctl", "--user", "daemon-reload"],
                    capture_output=True,
                )
            removed_items.append(f"Removed service file: {service_path}")
        except Exception as exc:
            errors.append(f"Failed to remove {service_path}: {exc}")

    service_dir = livekit_service_dir()
    if service_dir.exists():
        try:
            shutil.rmtree(service_dir)
            removed_items.append(f"Removed install directory: {service_dir}")
        except OSError as exc:
            errors.append(f"Failed to remove {service_dir}: {exc}")

    try:
        _remove_env_entries(voicemode_base_dir() / "voicemode.env")
        removed_items.append("Removed LiveKit environment entries")
    except OSError as exc:
        errors.append(f"Failed to update voicemode.env: {exc}")

    if remove_all_data and livekit_log_dir().exists():
        try:
            shutil.rmtree(livekit_log_dir())
            removed_items.append(f"Removed log directory: {livekit_log_dir()}")
        except OSError as exc:
            errors.append(f"Failed to remove {livekit_log_dir()}: {exc}")

    return {
        "success": not errors,
        "message": (
            "LiveKit uninstalled cleanly"
            if not errors
            else "LiveKit uninstall completed with errors"
        ),
        "removed_items": removed_items,
        "errors": errors,
    }
