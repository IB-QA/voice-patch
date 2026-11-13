"""Focused tests for the managed LiveKit service lifecycle."""

import io
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli
from voice_mode.livekit import LiveKitConfigurationError
from voice_mode.tools import determine_tools_to_load, get_all_available_tools
from voice_mode.tools.livekit import install as install_module
from voice_mode.tools.livekit import rooms as rooms_module
from voice_mode.tools.livekit import uninstall as uninstall_module
from voice_mode.tools.service import get_service_config_vars, service as service_tool
from voice_mode.utils.services import livekit_helpers


livekit_install = getattr(install_module.livekit_install, "fn", install_module.livekit_install)
livekit_uninstall = getattr(
    uninstall_module.livekit_uninstall,
    "fn",
    uninstall_module.livekit_uninstall,
)
service = getattr(service_tool, "fn", service_tool)
livekit_rooms = getattr(rooms_module.livekit_rooms, "fn", rooms_module.livekit_rooms)


def _archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                payload = content.encode()
                info.size = len(payload)
                info.mode = 0o755
                bundle.addfile(info, io.BytesIO(payload))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = content
                bundle.addfile(info)
    return buffer.getvalue()


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path / ".voicemode"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_helper_paths_and_configured_port(isolated_home):
    assert livekit_helpers.livekit_service_dir() == (
        isolated_home / ".voicemode" / "services" / "livekit"
    )
    config = livekit_helpers.livekit_config_path()
    config.parent.mkdir(parents=True)
    config.write_text("port: 7999\n")
    assert livekit_helpers.read_livekit_port() == 7999


def test_safe_extraction_accepts_only_regular_server(tmp_path):
    destination = tmp_path / "livekit-server"
    install_module._safe_extract_server(
        _archive([("livekit-server", "binary", "file")]),
        destination,
    )
    assert destination.read_text() == "binary"
    assert destination.stat().st_mode & 0o777 == 0o755

    with pytest.raises(ValueError, match="Unsafe archive path"):
        install_module._safe_extract_server(
            _archive([("../livekit-server", "bad", "file")]),
            destination,
        )
    with pytest.raises(ValueError, match="links are not allowed"):
        install_module._safe_extract_server(
            _archive([("livekit-server", "/tmp/evil", "symlink")]),
            destination,
        )


def test_linux_download_rejects_checksum_mismatch(isolated_home, monkeypatch):
    response = io.BytesIO(b"not the published archive")
    monkeypatch.setattr(
        install_module.urllib.request,
        "urlopen",
        lambda request, timeout: response,
    )
    monkeypatch.setattr(install_module.platform, "machine", lambda: "x86_64")
    with pytest.raises(ValueError, match="checksum mismatch"):
        install_module._download_linux_binary("1.13.6")


@pytest.mark.asyncio
async def test_install_preserves_config_and_credentials(isolated_home, monkeypatch):
    base = isolated_home / ".voicemode"
    base.mkdir(mode=0o700)
    env_path = base / "voicemode.env"
    env_path.write_text(
        "UNRELATED=value\n"
        "VOICEMODE_LIVEKIT_API_KEY=existing-key\n"
        "VOICEMODE_LIVEKIT_API_SECRET=existing-secret\n"
        "VOICEMODE_LIVEKIT_BROWSER_TOKEN=existing-browser-token\n"
    )
    os.chmod(env_path, 0o600)

    binary = base / "services" / "livekit" / "bin" / "livekit-server"

    def fake_download(version):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("binary")
        os.chmod(binary, 0o755)
        return binary

    monkeypatch.setattr(install_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install_module, "_download_linux_binary", fake_download)

    result = await livekit_install(auto_enable=False)

    assert result["success"] is True
    assert "UNRELATED=value" in env_path.read_text()
    assert "VOICEMODE_LIVEKIT_API_KEY=existing-key" in env_path.read_text()
    assert "VOICEMODE_LIVEKIT_API_SECRET=existing-secret" in env_path.read_text()
    assert (
        "VOICEMODE_LIVEKIT_BROWSER_TOKEN=existing-browser-token"
        in env_path.read_text()
    )
    config_path = livekit_helpers.livekit_config_path()
    config = yaml.safe_load(config_path.read_text())
    assert config["bind_addresses"] == ["127.0.0.1"]
    assert config["rtc"]["port_range_start"] == 50000
    assert config["rtc"]["port_range_end"] == 50100
    assert config["keys"] == {"existing-key": "existing-secret"}
    assert config_path.stat().st_mode & 0o777 == 0o600
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert result["browser_service_path"].endswith("voicemode-livekit-web.service")
    assert livekit_helpers.livekit_service_dir().stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
async def test_install_rotates_credentials(isolated_home, monkeypatch):
    base = isolated_home / ".voicemode"
    base.mkdir()
    (base / "voicemode.env").write_text(
        "VOICEMODE_LIVEKIT_API_KEY=old\n"
        "VOICEMODE_LIVEKIT_API_SECRET=old-secret\n"
    )
    binary = base / "services" / "livekit" / "bin" / "livekit-server"

    def fake_download(version):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("binary")
        return binary

    monkeypatch.setattr(install_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install_module, "_download_linux_binary", fake_download)
    result = await livekit_install(rotate_credentials=True, auto_enable=False)

    config = yaml.safe_load(livekit_helpers.livekit_config_path().read_text())
    key, secret = next(iter(config["keys"].items()))
    assert key != "old"
    assert secret != "old-secret"
    assert len(secret) >= 22
    assert result["credentials_rotated"] is True
    env_text = (base / "voicemode.env").read_text()
    browser_line = next(
        line
        for line in env_text.splitlines()
        if line.startswith("VOICEMODE_LIVEKIT_BROWSER_TOKEN=")
    )
    assert len(browser_line.split("=", 1)[1]) >= 22
    assert browser_line.split("=", 1)[1] not in str(result)


@pytest.mark.asyncio
async def test_uninstall_preserves_unrelated_env_and_logs_by_default(
    isolated_home,
    monkeypatch,
):
    base = isolated_home / ".voicemode"
    service_dir = base / "services" / "livekit"
    log_dir = base / "logs" / "livekit"
    service_dir.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    env_path = base / "voicemode.env"
    env_path.write_text(
        "KEEP=yes\n"
        "VOICEMODE_LIVEKIT_API_KEY=remove\n"
        "VOICEMODE_LIVEKIT_API_SECRET=remove\n"
        "VOICEMODE_LIVEKIT_BROWSER_TOKEN=remove-browser\n"
    )
    monkeypatch.setattr(uninstall_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(uninstall_module, "find_livekit_process", lambda: None)

    result = await livekit_uninstall()

    assert result["success"] is True
    assert not service_dir.exists()
    assert log_dir.exists()
    assert env_path.read_text() == "KEEP=yes\n"


@pytest.mark.asyncio
async def test_service_livekit_status_rejects_wrong_process(monkeypatch):
    monkeypatch.setattr(
        "voice_mode.tools.service.livekit_health",
        lambda: {
            "healthy": False,
            "port": 7880,
            "port_reachable": True,
            "process_matches": False,
            "pid": None,
        },
    )
    monkeypatch.setattr("voice_mode.tools.service.find_livekit_process", lambda port: None)
    result = await service("livekit", "status")
    assert "not available" in result.lower()


@pytest.mark.asyncio
async def test_rooms_returns_structured_typed_error(monkeypatch):
    def invalid_config():
        raise LiveKitConfigurationError("credentials_missing", "Credentials missing")

    monkeypatch.setattr(
        rooms_module.LiveKitConfig,
        "from_env",
        classmethod(lambda cls: invalid_config()),
    )
    result = await livekit_rooms()
    assert result == {
        "success": False,
        "error": {
            "code": "credentials_missing",
            "message": "Credentials missing",
        },
    }


def test_service_metadata_and_templates(isolated_home, monkeypatch):
    variables = get_service_config_vars("livekit")
    assert variables["START_SCRIPT"].endswith("start-livekit-server.sh")
    launchd = (
        Path(__file__).parents[1]
        / "voice_mode"
        / "templates"
        / "launchd"
        / "com.voicemode.livekit.plist"
    ).read_text()
    systemd = (
        Path(__file__).parents[1]
        / "voice_mode"
        / "templates"
        / "systemd"
        / "voicemode-livekit.service"
    ).read_text()
    assert "KeepAlive" in launchd
    assert "SuccessfulExit" in launchd
    assert "Restart=on-failure" in systemd
    assert "KillSignal=SIGTERM" in systemd
    assert "--dev" not in launchd + systemd
    web_variables = get_service_config_vars("livekit_web")
    assert web_variables["START_SCRIPT"].endswith("start-livekit-browser.sh")
    web_systemd = (
        Path(__file__).parents[1]
        / "voice_mode"
        / "templates"
        / "systemd"
        / "voicemode-livekit-web.service"
    ).read_text()
    assert "Restart=on-failure" in web_systemd
    assert "voicemode-livekit.service" in web_systemd


def test_tool_filtering_keeps_default_surface(monkeypatch):
    for name in (
        "VOICEMODE_TOOLS",
        "VOICEMODE_TOOLS_ENABLED",
        "VOICEMODE_TOOLS_DISABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    available = get_all_available_tools()
    assert {"livekit_install", "livekit_uninstall", "livekit_rooms"} <= available
    selected, _ = determine_tools_to_load()
    assert selected == {"converse", "service"}


def test_cli_exposes_unified_livekit_lifecycle():
    runner = CliRunner()
    result = runner.invoke(voice_mode_main_cli, ["service", "--help"])
    assert result.exit_code == 0
    assert "uninstall" in result.output
    install_help = runner.invoke(
        voice_mode_main_cli,
        ["service", "install", "--help"],
    )
    assert install_help.exit_code == 0
    assert "livekit" in install_help.output
    livekit_help = runner.invoke(
        voice_mode_main_cli,
        ["service", "install", "livekit", "--help"],
    )
    assert livekit_help.exit_code == 0
    assert "--rotate-credentials" in livekit_help.output
    start_help = runner.invoke(
        voice_mode_main_cli,
        ["service", "start", "--help"],
    )
    assert start_help.exit_code == 0
    start_command = voice_mode_main_cli.commands["service"].commands["start"]
    assert "livekit-web" in start_command.params[0].type.choices
