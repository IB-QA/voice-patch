"""Tests for voicemode plugin install."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli
from voice_mode.cli_commands import plugin as plugin_mod


def _dummy_binary(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_plugin_install_help() -> None:
    runner = CliRunner()
    result = runner.invoke(voice_mode_main_cli, ["plugin", "install", "--help"])
    assert result.exit_code == 0
    assert "--client" in result.output
    assert "--converse-hooks" in result.output
    assert "mcp.json" in result.output.lower() or "hooks.json" in result.output.lower()


def test_plugin_install_cursor_to_tmp(tmp_path: Path, monkeypatch) -> None:
    dummy = _dummy_binary(tmp_path / "src" / "voicemode_hook")
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", dummy)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.setattr(plugin_mod, "ensure_cached_hook_binary", lambda: dummy)

    out = tmp_path / "plugins"
    (out / "cursor").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        [
            "plugin",
            "install",
            "--client=cursor",
            "--converse-hooks",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    dest = out / "cursor" / "voicemode"
    assert (dest / ".cursor-plugin" / "plugin.json").is_file()
    assert (dest / "hooks" / "hooks.json").is_file()
    assert (dest / "skills" / "voicemode" / "SKILL.md").is_file()
    assert (dest / "commands" / "voicemode-plugin.md").is_file()
    assert (dest / "bin" / plugin_mod.HOOK_BIN_NAME).is_file()
    payload = json.loads((dest / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = payload["hooks"]["preToolUse"][0]["command"]
    assert "CURSOR_PLUGIN_ROOT" in command
    assert "--client=cursor" in command
    assert (dest / ".mcp.json").is_file()
    assert not (out / "mcp.json").exists()
    user_hooks = json.loads((out / "cursor" / "user-hooks.json").read_text())
    assert user_hooks["hooks"]["preToolUse"][0]["matcher"] == "MCP:converse"
    assert "voicemode_hook" in user_hooks["hooks"]["preToolUse"][0]["command"]
    assert "hooks:" in result.output
    assert "mcp:" in result.output
    user_mcp = json.loads((out / "cursor" / "user-mcp.json").read_text())
    assert user_mcp["mcpServers"]["voicemode"]["command"]


def test_plugin_install_all_clients_share_chatgpt_with_codex(tmp_path: Path, monkeypatch) -> None:
    dummy = _dummy_binary(tmp_path / "src" / "voicemode_hook")
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", dummy)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.setattr(plugin_mod, "ensure_cached_hook_binary", lambda: dummy)

    out = tmp_path / "plugins"
    for name in plugin_mod.CLIENTS:
        (out / name).mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=all", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert (out / "cursor" / "voicemode" / ".cursor-plugin" / "plugin.json").is_file()
    assert (out / "claude" / "voicemode" / ".claude-plugin" / "plugin.json").is_file()
    assert (out / "copilot" / "voicemode" / "plugin.json").is_file()
    assert (out / "codex" / "voicemode" / ".mcp.json").is_file()
    assert not (out / "chatgpt" / "voicemode").exists()
    assert (out / "devin" / "voicemode" / "hooks" / "hooks.v1.json").is_file()
    agy = json.loads((out / "antigravity" / "voicemode" / "hooks" / "hooks.json").read_text())
    assert "voicemode-converse" in agy
    assert agy["voicemode-converse"]["PreInvocation"][0]["type"] == "command"
    cfg_mcp = json.loads((out / "antigravity" / "config" / "mcp_config.json").read_text())
    assert "voicemode" in cfg_mcp["mcpServers"]
    assert cfg_mcp["mcpServers"]["voicemode"]["command"]
    cfg_hooks = json.loads((out / "antigravity" / "config" / "hooks.json").read_text())
    assert "voicemode-converse" in cfg_hooks
    assert "shares" in result.output
    cursor_mcp = json.loads((out / "cursor" / "user-mcp.json").read_text())
    assert "voicemode" in cursor_mcp["mcpServers"]
    claude_hooks = json.loads((out / "claude" / "user-hooks.json").read_text())
    assert claude_hooks["hooks"]["PreToolUse"][0]["matcher"] == "converse|converse_continue|mcp__.*converse"
    claude_mcp = json.loads((out / "claude" / "user-mcp.json").read_text())
    assert claude_mcp["mcpServers"]["voicemode"]["command"]
    copilot_hooks = json.loads((out / "copilot" / "hooks" / "voicemode-converse.json").read_text())
    assert "--client=copilot" in copilot_hooks["hooks"]["preToolUse"][0]["bash"]
    copilot_mcp = json.loads((out / "copilot" / "user-mcp.json").read_text())
    assert copilot_mcp["mcpServers"]["voicemode"]["type"] == "local"
    codex_hooks = json.loads((out / "codex" / "user-hooks.json").read_text())
    assert "voicemode_hook" in codex_hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--client=codex" in codex_hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    codex_toml = (out / "codex" / "config.toml").read_text()
    assert "[mcp_servers.voicemode]" in codex_toml
    assert 'command = "' in codex_toml
    devin_hooks = json.loads((out / "devin" / "user-hooks.json").read_text())
    assert "PreToolUse" in devin_hooks
    assert "voicemode_hook" in devin_hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert (out / "cursor" / "user-hooks.json").is_file()
    assert not (out / "chatgpt" / "user-hooks.json").exists()


def test_antigravity_merges_existing_mcp_servers(tmp_path: Path, monkeypatch) -> None:
    dummy = _dummy_binary(tmp_path / "src" / "voicemode_hook")
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", dummy)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.setattr(plugin_mod, "ensure_cached_hook_binary", lambda: dummy)

    cfg = tmp_path / "gemini-config"
    cfg.mkdir()
    (cfg / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"keep-me": {"command": "npx", "args": ["x"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICEMODE_ANTIGRAVITY_CONFIG", str(cfg))

    out = tmp_path / "plugins"
    (out / "antigravity").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=antigravity", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    merged = json.loads((cfg / "mcp_config.json").read_text())
    assert merged["mcpServers"]["keep-me"]["command"] == "npx"
    assert "voicemode" in merged["mcpServers"]
    hooks = json.loads((cfg / "hooks.json").read_text())
    assert "voicemode-converse" in hooks
    assert "mcp:" in result.output
    assert "hooks:" in result.output


def test_cursor_merges_user_hooks_without_dropping_others(tmp_path: Path, monkeypatch) -> None:
    dummy = _dummy_binary(tmp_path / "src" / "voicemode_hook")
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", dummy)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.setattr(plugin_mod, "ensure_cached_hook_binary", lambda: dummy)

    user_hooks = tmp_path / "cursor-user-hooks.json"
    user_hooks.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "sessionStart": [{"command": "keep-me"}],
                    "preToolUse": [
                        {
                            "command": "old/voicemode_hook --client=cursor",
                            "matcher": "MCP:converse",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICEMODE_CURSOR_HOOKS", str(user_hooks))

    out = tmp_path / "plugins"
    (out / "cursor").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=cursor", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    merged = json.loads(user_hooks.read_text())
    assert merged["hooks"]["sessionStart"][0]["command"] == "keep-me"
    pre = merged["hooks"]["preToolUse"]
    assert len(pre) == 1
    assert pre[0]["matcher"] == "MCP:converse"
    assert "old/voicemode_hook" not in pre[0]["command"]
    assert "voicemode_hook" in pre[0]["command"]


def _prime_plugin(monkeypatch, tmp_path: Path):
    dummy = _dummy_binary(tmp_path / "src" / "voicemode_hook")
    monkeypatch.setattr(plugin_mod, "PACKAGED_BINARY", dummy)
    monkeypatch.setattr(plugin_mod, "BUILD_SH", tmp_path / "missing-build.sh")
    monkeypatch.setattr(plugin_mod, "ensure_cached_hook_binary", lambda: dummy)
    return dummy


def test_claude_merges_settings_and_mcp_without_dropping_others(tmp_path: Path, monkeypatch) -> None:
    _prime_plugin(monkeypatch, tmp_path)
    settings = tmp_path / "claude-settings.json"
    settings.write_text(
        json.dumps(
            {
                "model": "keep-model",
                "hooks": {
                    "PostToolUse": [{"hooks": [{"type": "command", "command": "keep-post"}]}],
                    "PreToolUse": [
                        {
                            "matcher": "Grep",
                            "hooks": [{"type": "command", "command": "keep-grep"}],
                        },
                        {
                            "matcher": "converse",
                            "hooks": [{"type": "command", "command": "old/voicemode_hook"}],
                        },
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    mcp = tmp_path / "claude.json"
    mcp.write_text(
        json.dumps(
            {
                "numStartups": 1,
                "mcpServers": {
                    "voicemode-cli": {"command": "voicemode"},
                    "keep-me": {"command": "npx"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICEMODE_CLAUDE_HOOKS", str(settings))
    monkeypatch.setenv("VOICEMODE_CLAUDE_MCP", str(mcp))
    out = tmp_path / "plugins"
    (out / "claude").mkdir(parents=True)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=claude", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    merged_settings = json.loads(settings.read_text())
    assert merged_settings["model"] == "keep-model"
    assert merged_settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "keep-post"
    pre = merged_settings["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "Grep"
    assert pre[0]["hooks"][0]["command"] == "keep-grep"
    assert len(pre) == 2
    assert "old/voicemode_hook" not in pre[1]["hooks"][0]["command"]
    assert "voicemode_hook" in pre[1]["hooks"][0]["command"]
    merged_mcp = json.loads(mcp.read_text())
    assert merged_mcp["numStartups"] == 1
    assert merged_mcp["mcpServers"]["keep-me"]["command"] == "npx"
    assert merged_mcp["mcpServers"]["voicemode-cli"]["command"] == "voicemode"
    assert "voicemode" in merged_mcp["mcpServers"]


def test_copilot_writes_hook_file_and_merges_mcp(tmp_path: Path, monkeypatch) -> None:
    _prime_plugin(monkeypatch, tmp_path)
    other_hook = tmp_path / "copilot-hooks" / "codebase-memory-mcp.json"
    other_hook.parent.mkdir()
    other_hook.write_text(json.dumps({"version": 1, "hooks": {"sessionStart": [{"bash": "keep-me"}]}}))
    hook_file = tmp_path / "copilot-hooks" / "voicemode-converse.json"
    mcp = tmp_path / "copilot-mcp.json"
    mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "keep-me": {"command": "npx", "type": "stdio"},
                    "voicemode": {
                        "tools": ["*"],
                        "timeout": 600000,
                        "type": "local",
                        "command": "old-voicemode",
                        "args": [],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICEMODE_COPILOT_HOOKS", str(hook_file))
    monkeypatch.setenv("VOICEMODE_COPILOT_MCP", str(mcp))
    out = tmp_path / "plugins"
    (out / "copilot").mkdir(parents=True)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=copilot", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(other_hook.read_text())["hooks"]["sessionStart"][0]["bash"] == "keep-me"
    payload = json.loads(hook_file.read_text())
    assert "--client=copilot" in payload["hooks"]["preToolUse"][0]["bash"]
    assert "powershell" in payload["hooks"]["preToolUse"][0]
    merged = json.loads(mcp.read_text())
    assert merged["mcpServers"]["keep-me"]["command"] == "npx"
    assert merged["mcpServers"]["voicemode"]["type"] == "local"
    assert merged["mcpServers"]["voicemode"]["timeout"] == 600000
    assert merged["mcpServers"]["voicemode"]["command"] != "old-voicemode"


def test_codex_merges_hooks_and_appends_toml_mcp(tmp_path: Path, monkeypatch) -> None:
    _prime_plugin(monkeypatch, tmp_path)
    hooks = tmp_path / "codex-hooks.json"
    hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionEnd": [{"hooks": [{"type": "command", "command": "keep-end"}]}],
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": "keep-star"}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    toml_path = tmp_path / "config.toml"
    toml_path.write_text('model = "keep-me"\n[mcp_servers.other]\ncommand = "npx"\n', encoding="utf-8")
    monkeypatch.setenv("VOICEMODE_CODEX_HOOKS", str(hooks))
    monkeypatch.setenv("VOICEMODE_CODEX_MCP", str(toml_path))
    out = tmp_path / "plugins"
    (out / "codex").mkdir(parents=True)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=codex", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    merged = json.loads(hooks.read_text())
    assert merged["hooks"]["SessionEnd"][0]["hooks"][0]["command"] == "keep-end"
    pre = merged["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "*"
    assert pre[0]["hooks"][0]["command"] == "keep-star"
    assert "voicemode_hook" in pre[1]["hooks"][0]["command"]
    text = toml_path.read_text()
    assert 'model = "keep-me"' in text
    assert "[mcp_servers.other]" in text
    assert "[mcp_servers.voicemode]" in text
    result2 = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=codex", "--converse-hooks", "--output", str(out)],
    )
    assert result2.exit_code == 0, result2.output
    assert toml_path.read_text().count("[mcp_servers.voicemode]") == 1


def test_cursor_merges_user_mcp_without_dropping_others(tmp_path: Path, monkeypatch) -> None:
    _prime_plugin(monkeypatch, tmp_path)
    mcp = tmp_path / "cursor-mcp.json"
    mcp.write_text(
        json.dumps({"mcpServers": {"keep-me": {"command": "npx"}, "voicemode": {"command": "old"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICEMODE_CURSOR_MCP", str(mcp))
    out = tmp_path / "plugins"
    (out / "cursor").mkdir(parents=True)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=cursor", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    merged = json.loads(mcp.read_text())
    assert merged["mcpServers"]["keep-me"]["command"] == "npx"
    assert merged["mcpServers"]["voicemode"]["command"] != "old"


def test_devin_merges_user_hooks_v1_and_skips_invented_mcp(tmp_path: Path, monkeypatch) -> None:
    _prime_plugin(monkeypatch, tmp_path)
    hooks = tmp_path / "devin-hooks.v1.json"
    hooks.write_text(
        json.dumps(
            {
                "PreToolUse": [
                    {
                        "matcher": "Keep",
                        "hooks": [{"type": "command", "command": "keep-me"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICEMODE_DEVIN_HOOKS", str(hooks))
    out = tmp_path / "plugins"
    (out / "devin").mkdir(parents=True)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=devin", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    merged = json.loads(hooks.read_text())
    assert merged["PreToolUse"][0]["hooks"][0]["command"] == "keep-me"
    assert "voicemode_hook" in merged["PreToolUse"][1]["hooks"][0]["command"]
    assert not (out / "devin" / "user-mcp.json").exists()
    assert "mcp:" not in result.output


def test_chatgpt_wires_codex_user_paths(tmp_path: Path, monkeypatch) -> None:
    _prime_plugin(monkeypatch, tmp_path)
    out = tmp_path / "plugins"
    (out / "codex").mkdir(parents=True)
    result = CliRunner().invoke(
        voice_mode_main_cli,
        ["plugin", "install", "--client=chatgpt", "--converse-hooks", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert (out / "codex" / "voicemode" / "plugin.json").is_file()
    assert (out / "codex" / "user-hooks.json").is_file()
    assert "[mcp_servers.voicemode]" in (out / "codex" / "config.toml").read_text()
    assert not (out / "chatgpt" / "voicemode").exists()
