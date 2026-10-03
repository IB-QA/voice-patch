"""Secure installer for the managed LiveKit SFU service."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from voice_mode.config import SERVICE_AUTO_ENABLE
from voice_mode.server import mcp
from voice_mode.utils.services.livekit_helpers import (
    DEFAULT_LIVEKIT_PORT,
    DEFAULT_RTC_PORT_END,
    DEFAULT_RTC_PORT_START,
    livekit_config_path,
    livekit_browser_start_script_path,
    livekit_log_dir,
    livekit_metadata_path,
    livekit_service_dir,
    livekit_start_script_path,
    voicemode_base_dir,
)


DEFAULT_LIVEKIT_VERSION = "1.13.6"
LINUX_RELEASES = {
    "x86_64": (
        "amd64",
        "2b61abef2b9ba14b4b8ca38b37de9a37ffc682b9931d5fc03ceca2f0b77d3e33",
    ),
    "amd64": (
        "amd64",
        "2b61abef2b9ba14b4b8ca38b37de9a37ffc682b9931d5fc03ceca2f0b77d3e33",
    ),
    "aarch64": (
        "arm64",
        "5c75f09173199f3f8fe0c3c0d5a41171f9b306ffce6843d752c276d11e77d19b",
    ),
    "arm64": (
        "arm64",
        "5c75f09173199f3f8fe0c3c0d5a41171f9b306ffce6843d752c276d11e77d19b",
    ),
}
ENV_KEYS = (
    "VOICEMODE_LIVEKIT_URL",
    "VOICEMODE_LIVEKIT_API_KEY",
    "VOICEMODE_LIVEKIT_API_SECRET",
    "VOICEMODE_LIVEKIT_BROWSER_TOKEN",
)
logger = logging.getLogger("voicemode")


def _atomic_write(path: Path, content: str | bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    binary = isinstance(content, bytes)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb" if binary else "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines: list[str] = []
    values: dict[str, str] = {}
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return lines, values


def _update_env(path: Path, updates: dict[str, str]) -> None:
    lines, _ = _read_env(path)
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in updates:
            if key in remaining:
                output.append(f"{key}={shlex.quote(remaining.pop(key))}")
        else:
            output.append(line)
    output.extend(f"{key}={shlex.quote(value)}" for key, value in remaining.items())
    _atomic_write(path, "\n".join(output).rstrip() + "\n", 0o600)


def _safe_extract_server(archive: bytes, destination: Path) -> None:
    """Extract only a regular ``livekit-server`` file from a trusted archive."""

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        candidates = []
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"Archive links are not allowed: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Unsupported archive entry: {member.name}")
            if path.name == "livekit-server":
                candidates.append(member)
        if len(candidates) != 1:
            raise ValueError("Archive must contain exactly one livekit-server binary")
        source = bundle.extractfile(candidates[0])
        if source is None:
            raise ValueError("Could not read livekit-server from archive")
        _atomic_write(destination, source.read(), 0o755)


def _download_linux_binary(version: str) -> Path:
    if version != DEFAULT_LIVEKIT_VERSION:
        raise ValueError(
            f"No embedded checksum is available for LiveKit Server {version}"
        )
    release = LINUX_RELEASES.get(platform.machine().lower())
    if release is None:
        raise ValueError(f"Unsupported Linux architecture: {platform.machine()}")
    architecture, expected_hash = release
    url = (
        "https://github.com/livekit/livekit/releases/download/"
        f"v{version}/livekit_{version}_linux_{architecture}.tar.gz"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "voicemode-livekit"})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = response.read()
    actual_hash = hashlib.sha256(archive).hexdigest()
    if not secrets.compare_digest(actual_hash, expected_hash):
        raise ValueError(
            f"LiveKit archive checksum mismatch: expected {expected_hash}, "
            f"received {actual_hash}"
        )
    binary = livekit_service_dir() / "bin" / "livekit-server"
    _safe_extract_server(archive, binary)
    return binary


def _parse_server_version(version_text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", version_text)
    if match is None:
        return None
    return match.group(1)


def _install_macos_binary(version: str) -> tuple[Path, str]:
    brew = shutil.which("brew")
    if brew is None:
        raise ValueError(
            "Homebrew is required on macOS; install it, then run "
            "`brew install livekit`."
        )
    subprocess.run([brew, "install", "livekit"], check=True, capture_output=True)
    prefix_result = subprocess.run(
        [brew, "--prefix", "livekit"],
        check=True,
        capture_output=True,
        text=True,
    )
    prefix = Path(prefix_result.stdout.strip())
    candidates = (
        prefix / "bin" / "livekit-server",
        Path(shutil.which("livekit-server") or ""),
    )
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            resolved = candidate.resolve()
            version_result = subprocess.run(
                [str(resolved), "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            reported = f"{version_result.stdout}\n{version_result.stderr}"
            actual = _parse_server_version(reported)
            if actual is None:
                raise ValueError(
                    "Homebrew livekit-server did not report a usable version"
                )
            # Homebrew owns the macOS pin. Record what brew actually installed
            # instead of failing when the formula moved past DEFAULT_LIVEKIT_VERSION.
            if version != actual:
                logger.info(
                    "Homebrew livekit-server is %s (installer default %s)",
                    actual,
                    version,
                )
            return resolved, actual
    raise ValueError("Homebrew installed livekit but livekit-server was not found")


def _render_config(api_key: str, api_secret: str) -> str:
    config = {
        "port": DEFAULT_LIVEKIT_PORT,
        "bind_addresses": ["127.0.0.1"],
        "rtc": {
            "port_range_start": DEFAULT_RTC_PORT_START,
            "port_range_end": DEFAULT_RTC_PORT_END,
            "use_external_ip": False,
        },
        "keys": {api_key: api_secret},
    }
    return yaml.safe_dump(config, sort_keys=False)


def _write_start_script(binary: Path) -> Path:
    template = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "scripts"
        / "start-livekit-server.sh"
    )
    script = template.read_text(encoding="utf-8").format(
        LIVEKIT_BINARY=shlex.quote(str(binary)),
        LIVEKIT_CONFIG=shlex.quote(str(livekit_config_path())),
    )
    path = livekit_start_script_path()
    _atomic_write(path, script, 0o700)
    return path


def _write_browser_start_script() -> Path:
    template = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "scripts"
        / "start-livekit-browser.sh"
    )
    script = template.read_text(encoding="utf-8").format(
        ENV_FILE=shlex.quote(
            str(voicemode_base_dir() / "voicemode.env"),
        ),
        PYTHON=shlex.quote(sys.executable),
    )
    path = livekit_browser_start_script_path()
    _atomic_write(path, script, 0o700)
    return path


def _write_service_file() -> Path:
    root = Path(__file__).resolve().parents[2] / "templates"
    if platform.system() == "Darwin":
        source = root / "launchd" / "com.voicemode.livekit.plist"
        destination = (
            Path.home() / "Library" / "LaunchAgents" / "com.voicemode.livekit.plist"
        )
    else:
        source = root / "systemd" / "voicemode-livekit.service"
        destination = (
            Path.home() / ".config" / "systemd" / "user" / "voicemode-livekit.service"
        )
    content = source.read_text(encoding="utf-8").format(
        HOME=str(Path.home()),
        START_SCRIPT=str(livekit_start_script_path()),
        LIVEKIT_DIR=str(livekit_service_dir()),
        LOG_DIR=str(livekit_log_dir()),
    )
    _atomic_write(destination, content, 0o600)
    return destination


def _write_browser_service_file() -> Path:
    root = Path(__file__).resolve().parents[2] / "templates"
    if platform.system() == "Darwin":
        source = root / "launchd" / "com.voicemode.livekit-web.plist"
        destination = (
            Path.home()
            / "Library"
            / "LaunchAgents"
            / "com.voicemode.livekit-web.plist"
        )
    else:
        source = root / "systemd" / "voicemode-livekit-web.service"
        destination = (
            Path.home()
            / ".config"
            / "systemd"
            / "user"
            / "voicemode-livekit-web.service"
        )
    content = source.read_text(encoding="utf-8").format(
        START_SCRIPT=str(livekit_browser_start_script_path()),
        LIVEKIT_DIR=str(livekit_service_dir()),
        LOG_DIR=str(livekit_log_dir()),
    )
    _atomic_write(destination, content, 0o600)
    return destination


def _enable_service(service_path: Path) -> None:
    if platform.system() == "Darwin":
        subprocess.run(
            ["launchctl", "load", "-w", str(service_path)],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", service_path.name],
            check=True,
        )


@mcp.tool()
async def livekit_install(
    version: str = DEFAULT_LIVEKIT_VERSION,
    force_reinstall: bool = False,
    rotate_credentials: bool = False,
    auto_enable: bool | None = None,
) -> dict[str, Any]:
    """Install a loopback-only managed LiveKit Server."""

    try:
        system = platform.system()
        if system not in {"Darwin", "Linux"}:
            return {"success": False, "error": f"Unsupported platform: {system}"}

        service_dir = livekit_service_dir()
        log_dir = livekit_log_dir()
        for directory in (voicemode_base_dir(), service_dir, log_dir):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)

        env_path = voicemode_base_dir() / "voicemode.env"
        _, existing = _read_env(env_path)
        api_key = existing.get("VOICEMODE_LIVEKIT_API_KEY")
        api_secret = existing.get("VOICEMODE_LIVEKIT_API_SECRET")
        browser_token = existing.get("VOICEMODE_LIVEKIT_BROWSER_TOKEN")
        if rotate_credentials or not api_key or not api_secret:
            api_key = f"VM{secrets.token_urlsafe(12)}"
            api_secret = secrets.token_urlsafe(32)
        if not browser_token:
            browser_token = secrets.token_urlsafe(24)

        if system == "Darwin":
            binary, version = _install_macos_binary(version)
        else:
            binary = _download_linux_binary(version)
        _atomic_write(livekit_config_path(), _render_config(api_key, api_secret), 0o600)
        start_script = _write_start_script(binary)
        browser_start_script = _write_browser_start_script()
        source = "homebrew:livekit" if system == "Darwin" else "github-release"
        metadata = {
            "binary": str(binary),
            "version": version,
            "source": source,
        }
        _atomic_write(
            livekit_metadata_path(),
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            0o600,
        )
        _update_env(
            env_path,
            {
                "VOICEMODE_LIVEKIT_URL": f"ws://127.0.0.1:{DEFAULT_LIVEKIT_PORT}",
                "VOICEMODE_LIVEKIT_API_KEY": api_key,
                "VOICEMODE_LIVEKIT_API_SECRET": api_secret,
                "VOICEMODE_LIVEKIT_BROWSER_TOKEN": browser_token,
            },
        )
        service_path = _write_service_file()
        browser_service_path = _write_browser_service_file()
        should_enable = SERVICE_AUTO_ENABLE if auto_enable is None else auto_enable
        if should_enable:
            _enable_service(service_path)
            _enable_service(browser_service_path)
        return {
            "success": True,
            "install_path": str(service_dir),
            "binary": str(binary),
            "version": version,
            "config_path": str(livekit_config_path()),
            "start_script": str(start_script),
            "service_path": str(service_path),
            "browser_start_script": str(browser_start_script),
            "browser_service_path": str(browser_service_path),
            "port": DEFAULT_LIVEKIT_PORT,
            "credentials_rotated": bool(rotate_credentials),
            "auto_enabled": bool(should_enable),
        }
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        return {"success": False, "error": str(exc)}
