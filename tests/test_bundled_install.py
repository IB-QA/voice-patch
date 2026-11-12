"""Installing from a bundled wheel, and keeping a copy of tool settings before merging."""

import json
import subprocess
import sys
from pathlib import Path

INSTALLER_ROOT = Path(__file__).resolve().parents[1] / "installer"
sys.path.insert(0, str(INSTALLER_ROOT))

from voicemode_install.installer import PackageInstaller
from voicemode_install.system import PlatformInfo

from voice_mode.cli_commands import plugin as plugin_mod
from voice_mode.cli_commands.plugin import merge_mcp_servers


def _installer():
    info = PlatformInfo(
        os_type="darwin",
        os_name="macOS",
        distribution="darwin",
        architecture="arm64",
    )
    return PackageInstaller(info)


def test_bundled_wheel_replaces_the_public_package(monkeypatch):
    calls = []
    monkeypatch.setenv("VOICEMODE_INSTALL_SOURCE", "/tmp/voice_mode-1.0-py3-none-any.whl")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    assert _installer().install_voicemode()
    assert calls == [["uv", "tool", "install", "--upgrade", "--force", "/tmp/voice_mode-1.0-py3-none-any.whl"]]


def test_without_a_bundle_the_public_package_is_used(monkeypatch):
    calls = []
    monkeypatch.delenv("VOICEMODE_INSTALL_SOURCE", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    assert _installer().install_voicemode()
    assert calls == [["uv", "tool", "install", "--upgrade", "voice-mode"]]


def test_merging_keeps_other_servers_and_a_backup(tmp_path):
    path = tmp_path / "mcp.json"
    original = {"mcpServers": {"other": {"command": "other-server"}}}
    path.write_text(json.dumps(original))

    merge_mcp_servers(path, {"voicemode": {"command": "voicemode-mcp"}})
    merge_mcp_servers(path, {"voicemode": {"command": "voicemode-mcp"}})

    merged = json.loads(path.read_text())
    assert merged["mcpServers"]["other"] == {"command": "other-server"}
    assert merged["mcpServers"]["voicemode"]["command"] == "voicemode-mcp"
    assert json.loads((tmp_path / "mcp.json.before-voicemode").read_text()) == original


def test_a_hook_built_for_another_platform_is_not_installed(tmp_path, monkeypatch):
    foreign = tmp_path / "voicemode_hook"
    foreign.write_bytes(b"\xcf\xfa\xed\xfe not for this machine")
    foreign.chmod(0o755)
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", foreign)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.setenv("VOICEMODE_HOOK_CACHE_DIR", str(tmp_path / "cache"))

    assert plugin_mod.ensure_cached_hook_binary() is None
    assert not (tmp_path / "cache" / "voicemode_hook").exists()
