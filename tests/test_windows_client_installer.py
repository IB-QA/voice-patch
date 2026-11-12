"""Windows client installer: detect the OS, skip local speech servers, require VAD."""

import platform
import sys
from pathlib import Path

INSTALLER_ROOT = Path(__file__).resolve().parents[1] / "installer"
sys.path.insert(0, str(INSTALLER_ROOT))

from voicemode_install.checker import DependencyChecker
from voicemode_install.clients import detect_installed_clients
from voicemode_install.hardware import HardwareInfo
from voicemode_install.system import PlatformInfo, detect_platform, get_package_manager


def test_windows_is_a_supported_platform(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")

    info = detect_platform()

    assert info.os_type == "windows"
    assert info.distribution == "windows"
    assert info.architecture == "x86_64"
    assert info.is_wsl is False
    assert get_package_manager(info.distribution) == "winget"


def test_windows_client_does_not_install_local_speech_servers():
    info = PlatformInfo(
        os_type="windows",
        os_name="Windows",
        distribution="windows",
        architecture="x86_64",
    )

    assert HardwareInfo(info).should_recommend_local_services() is False


def test_windows_core_dependency_is_ffmpeg_not_a_compiler():
    info = PlatformInfo(
        os_type="windows",
        os_name="Windows",
        distribution="windows",
        architecture="x86_64",
    )

    names = {pkg.name for pkg in DependencyChecker(info).check_core_dependencies()}

    assert names == {"ffmpeg"}
    assert "gcc" not in names
    assert "python3-dev" not in names


def test_detect_installed_clients_uses_config_directories(tmp_path: Path):
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()

    assert detect_installed_clients(tmp_path) == ["cursor", "claude", "codex"]
