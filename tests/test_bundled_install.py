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
    assert calls[0][1:] == ["tool", "install", "--upgrade", "--force", "/tmp/voice_mode-1.0-py3-none-any.whl"]
    assert calls[0][0].endswith("uv") or calls[0][0].endswith("uv.exe")


def test_without_a_bundle_the_public_package_is_used(monkeypatch):
    calls = []
    monkeypatch.delenv("VOICEMODE_INSTALL_SOURCE", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    assert _installer().install_voicemode()
    assert calls[0][1:] == ["tool", "install", "--upgrade", "voice-mode"]


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


def test_an_environment_variable_can_point_at_the_hook(tmp_path, monkeypatch):
    binary = tmp_path / "voicemode_hook"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("VOICEMODE_HOOK_BINARY", str(binary))
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", tmp_path / "absent")
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "absent.sh")

    assert plugin_mod.ensure_cached_hook_binary() == binary


def test_a_hook_built_for_another_platform_is_not_installed(tmp_path, monkeypatch):
    foreign = tmp_path / "voicemode_hook"
    foreign.write_bytes(b"\xcf\xfa\xed\xfe not for this machine")
    foreign.chmod(0o755)
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", foreign)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.delenv("VOICEMODE_HOOK_BINARY", raising=False)
    monkeypatch.setenv("VOICEMODE_HOOK_CACHE_DIR", str(tmp_path / "cache"))

    assert plugin_mod.ensure_cached_hook_binary() is None
    assert not (tmp_path / "cache" / "voicemode_hook").exists()


def test_uv_is_found_even_when_its_folder_is_not_on_path(tmp_path, monkeypatch):
    from voicemode_install import installer as installer_mod

    folder = tmp_path / ".local" / "bin"
    folder.mkdir(parents=True)
    (folder / "uv.exe").write_text("")
    monkeypatch.setattr(installer_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(installer_mod.Path, "home", lambda: tmp_path)

    assert installer_mod.find_uv() == str(folder / "uv.exe")


def test_the_install_also_puts_uv_tools_on_the_users_path(monkeypatch):
    calls = []
    monkeypatch.delenv("VOICEMODE_INSTALL_SOURCE", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    assert _installer().install_voicemode()
    assert calls[1][1:] == ["tool", "update-shell"]


def test_an_unattended_install_continues_when_system_packages_fail(monkeypatch, tmp_path):
    """A failed ffmpeg install must not stop VoiceMode and the tool setup."""
    from click.testing import CliRunner
    from voicemode_install import cli as cli_mod

    steps = []
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_mod, "ensure_homebrew_on_macos", lambda *a, **k: True)
    monkeypatch.setattr(cli_mod, "check_existing_installation", lambda: False)
    monkeypatch.setattr(cli_mod.PackageInstaller, "install_packages", lambda self, pkgs: False)
    monkeypatch.setattr(cli_mod.PackageInstaller, "install_voicemode", lambda self, version=None: steps.append("voicemode") or True)
    monkeypatch.setattr(cli_mod, "verify_silence_detection", lambda dry_run=False: True)
    monkeypatch.setattr(cli_mod, "attempt_optional_simpleaudio", lambda dry_run=False: "skipped")
    monkeypatch.setattr(cli_mod, "offer_client_hooks", lambda **k: steps.append("hooks"))

    class Missing:
        name, description, required, installed = "ffmpeg", "audio", True, False

    monkeypatch.setattr(cli_mod.DependencyChecker, "check_core_dependencies", lambda self: [Missing()])
    monkeypatch.setattr(cli_mod.DependencyChecker, "get_missing_packages", lambda self, deps: deps)
    monkeypatch.setattr(
        cli_mod.DependencyChecker, "get_summary", lambda self, deps: {"installed": 0, "missing_required": 1}
    )

    result = CliRunner().invoke(cli_mod.main, ["--yes", "--skip-services"])
    assert "voicemode" in steps and "hooks" in steps, result.output


def test_only_the_tools_the_user_picked_get_hooks(monkeypatch, tmp_path):
    """The graphical installer passes the tools the user ticked."""
    from voicemode_install import cli as cli_mod

    ran = []
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_mod, "detect_installed_clients", lambda home: ["cursor", "claude", "codex"])
    monkeypatch.setattr(cli_mod.shutil, "which", lambda name: "/bin/voicemode")
    monkeypatch.setattr(
        cli_mod.subprocess, "run",
        lambda cmd, **k: ran.append(cmd[cmd.index("--client") + 1]) or type("R", (), {"returncode": 0})(),
    )
    cli_mod.offer_client_hooks(dry_run=False, non_interactive=True, clients="cursor,codex")
    assert ran == ["cursor", "codex"]

    ran.clear()
    cli_mod.offer_client_hooks(dry_run=False, non_interactive=True, clients="none")
    assert ran == []


def test_mcp_entries_use_the_plain_command_name(monkeypatch):
    """Configs must say `voicemode`, not a full path to voicemode.exe."""
    from voice_mode.cli_commands import plugin

    monkeypatch.setattr(plugin.shutil, "which", lambda name: r"C:\Users\x\.local\bin\voicemode.exe")
    for client in ("cursor", "claude", "copilot", "codex", "generic"):
        assert plugin.mcp_server_entry(client)["command"] == "voicemode"


class _Done:
    def __init__(self, code=0, out=""):
        self.returncode, self.stdout, self.stderr = code, out, ""


def test_copilot_plugin_is_registered_with_the_copilot_cli(monkeypatch, tmp_path):
    from voice_mode.cli_commands import plugin

    monkeypatch.delenv("VOICEMODE_COPILOT_SKIP_PLUGIN_REGISTER")
    monkeypatch.setattr(plugin.shutil, "which", lambda name: "/bin/copilot")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[1:])
        return _Done(0, 'Plugin "voicemode" installed successfully.')

    monkeypatch.setattr(plugin.subprocess, "run", fake_run)
    assert plugin.register_copilot_plugin(tmp_path) is True
    assert calls == [["plugin", "uninstall", "voicemode"], ["plugin", "install", str(tmp_path)]]


def test_copilot_registration_falls_back_when_the_cli_is_missing_or_refuses(monkeypatch, tmp_path):
    from voice_mode.cli_commands import plugin

    monkeypatch.delenv("VOICEMODE_COPILOT_SKIP_PLUGIN_REGISTER")
    monkeypatch.setattr(plugin.shutil, "which", lambda name: None)
    assert plugin.register_copilot_plugin(tmp_path) is False

    monkeypatch.setattr(plugin.shutil, "which", lambda name: "/bin/copilot")
    monkeypatch.setattr(plugin.subprocess, "run", lambda cmd, **kw: _Done(1, "no"))
    assert plugin.register_copilot_plugin(tmp_path) is False


def test_registered_copilot_plugin_replaces_the_user_level_entries(monkeypatch, tmp_path):
    """The plugin carries the MCP server and hook; writing both would load them twice."""
    from voice_mode.cli_commands import plugin

    mcp = tmp_path / "mcp-config.json"
    hooks = tmp_path / "voicemode-converse.json"
    mcp.write_text('{"mcpServers": {"voicemode": {}, "other": {"command": "x"}}}')
    hooks.write_text("{}")
    monkeypatch.setenv("VOICEMODE_COPILOT_MCP", str(mcp))
    monkeypatch.setenv("VOICEMODE_COPILOT_HOOKS", str(hooks))
    monkeypatch.setattr(plugin, "register_copilot_plugin", lambda dest: True)

    written = plugin.wire_user_level("copilot", tmp_path / "plugin", None, True)

    assert written == [("plugin", tmp_path / "plugin")]
    assert json.loads(mcp.read_text())["mcpServers"] == {"other": {"command": "x"}}
    assert not hooks.exists()
