"""Install VoiceMode as a client plugin.

One command, one module. Client-specific hook JSON, plugin manifests, and a
bundled MCP entry are generated here — they are not committed as per-client
files in the repo. Templates (skills, commands) come from ``.agents/``.

Does user-level wiring for every client: merge that product's real
hooks and MCP config (other entries kept). Plugin folders are still
written. ChatGPT shares Codex user files.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import click

from voice_mode.__version__ import __version__ as VERSION

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
AGENTS_DIR = REPO_ROOT / ".agents"
PACKAGED_BINARY = PACKAGE_ROOT / "data" / "hooks" / "bin" / "voicemode_hook"
BUILD_SH = PACKAGE_ROOT / "data" / "hooks" / "reciever" / "build.sh"
HOOK_CACHE_DIR = Path.home() / ".voicemode" / "services" / "hooks"
HOOK_CACHE_BIN = HOOK_CACHE_DIR / "voicemode_hook"
HOOK_CACHE_STAMP = HOOK_CACHE_DIR / "voice_mode_version"

# Canonical names shown in --help and accepted by --client=all.
CLIENTS = (
    "cursor",
    "claude",
    "copilot",
    "antigravity",
    "codex",
    "chatgpt",
    "devin",
)

ALIASES = {
    "claude-code": "claude",
    "claude_code": "claude",
    "anthropic": "claude",
    "github": "copilot",
    "github-copilot": "copilot",
    "github_copilot": "copilot",
    "chat-gpt": "chatgpt",
    "openai": "chatgpt",
}

# Parent of the voicemode plugin folder. Override with VOICEMODE_PLUGIN_DIR_<CLIENT>.
DEFAULT_PARENTS = {
    "cursor": Path.home() / ".cursor" / "plugins" / "local",
    "claude": Path.home() / ".claude" / "plugins",
    "copilot": Path.home() / ".copilot" / "plugins",
    "antigravity": Path.home() / ".gemini" / "config" / "plugins",
    "codex": Path.home() / ".codex" / "plugins",
    "chatgpt": Path.home() / ".codex" / "plugins",
    "devin": Path.home() / ".devin" / "plugins",
}

# Used only to decide whether we may create the plugin parent.
CLIENT_APP_DIRS = {
    "cursor": Path.home() / ".cursor",
    "claude": Path.home() / ".claude",
    "copilot": Path.home() / ".copilot",
    "antigravity": Path.home() / ".gemini",
    "codex": Path.home() / ".codex",
    "chatgpt": Path.home() / ".codex",
    "devin": Path.home() / ".devin",
}

# Rust --client value. ChatGPT Codex uses the Codex schema.
HOOK_CLIENT = {
    "cursor": "cursor",
    "claude": "claude",
    "copilot": "copilot",
    "antigravity": "antigravity",
    "codex": "codex",
    "chatgpt": "codex",
    "devin": "devin",
}


ANTIGRAVITY_CONFIG = Path.home() / ".gemini" / "config"
CURSOR_USER_HOOKS = Path.home() / ".cursor" / "hooks.json"
CURSOR_USER_MCP = Path.home() / ".cursor" / "mcp.json"
CLAUDE_USER_HOOKS = Path.home() / ".claude" / "settings.json"
CLAUDE_USER_MCP = Path.home() / ".claude.json"
COPILOT_USER_HOOKS = Path.home() / ".copilot" / "hooks" / "voicemode-converse.json"
COPILOT_USER_MCP = Path.home() / ".copilot" / "mcp-config.json"
CODEX_USER_HOOKS = Path.home() / ".codex" / "hooks.json"
CODEX_USER_MCP = Path.home() / ".codex" / "config.toml"
DEVIN_USER_HOOKS = Path.home() / ".devin" / "hooks.v1.json"

CLAUDE_CONVERSE_MATCHER = "converse|converse_continue|mcp__.*converse"


def user_wire_name(client: str) -> str:
    return "codex" if client == "chatgpt" else client


def _env_path(key: str) -> Path | None:
    override = os.environ.get(key)
    if override:
        return Path(override).expanduser()
    return None


def antigravity_config_dir(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_ANTIGRAVITY_CONFIG")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "antigravity" / "config"
    return ANTIGRAVITY_CONFIG


def cursor_user_hooks_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_CURSOR_HOOKS")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "cursor" / "user-hooks.json"
    return CURSOR_USER_HOOKS


def cursor_user_mcp_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_CURSOR_MCP")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "cursor" / "user-mcp.json"
    return CURSOR_USER_MCP


def claude_user_hooks_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_CLAUDE_HOOKS")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "claude" / "user-hooks.json"
    return CLAUDE_USER_HOOKS


def claude_user_mcp_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_CLAUDE_MCP")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "claude" / "user-mcp.json"
    return CLAUDE_USER_MCP


def copilot_user_hooks_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_COPILOT_HOOKS")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "copilot" / "hooks" / "voicemode-converse.json"
    return COPILOT_USER_HOOKS


def copilot_user_mcp_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_COPILOT_MCP")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "copilot" / "user-mcp.json"
    return COPILOT_USER_MCP


def codex_user_hooks_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_CODEX_HOOKS")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "codex" / "user-hooks.json"
    return CODEX_USER_HOOKS


def codex_user_mcp_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_CODEX_MCP")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "codex" / "config.toml"
    return CODEX_USER_MCP


def devin_user_hooks_path(output: Path | None) -> Path:
    override = _env_path("VOICEMODE_DEVIN_HOOKS")
    if override is not None:
        return override
    if output is not None:
        return Path(output) / "devin" / "user-hooks.json"
    return DEVIN_USER_HOOKS


def voicemode_mcp_command() -> str:
    # Plain name, never a resolved path: a full path to voicemode.exe goes stale
    # when the tool is reinstalled or moved, and it is noisy in every config file.
    return "voicemode"


def parse_clients(raw: str) -> list[str]:
    text = (raw or "").strip().lower()
    if not text:
        raise click.ClickException("Pass --client=cursor or --client=all")
    if text in ("all", "*"):
        return list(CLIENTS)
    out: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        name = ALIASES.get(part.strip(), part.strip())
        if name not in CLIENTS:
            raise click.ClickException(
                f"Unknown client {part.strip()!r}. Valid: {', '.join(CLIENTS)}, all"
            )
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def plugin_parent(client: str, output: Path | None) -> Path:
    dest_client = "codex" if client == "chatgpt" else client
    if output is not None:
        return Path(output) / dest_client
    env_key = f"VOICEMODE_PLUGIN_DIR_{client.upper()}"
    override = os.environ.get(env_key)
    if override:
        return Path(override).expanduser()
    return DEFAULT_PARENTS[client]


def plugin_home(client: str, output: Path | None) -> Path:
    return plugin_parent(client, output) / "voicemode"


def hook_binary_runs(path: Path) -> bool:
    """The packaged binary is built for one platform; a hook that cannot start
    would block converse in clients whose hooks fail closed (Copilot)."""
    try:
        result = subprocess.run([str(path)], input="", capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ensure_cached_hook_binary() -> Path | None:
    """Return a hook binary that runs on this machine, or None if there is none."""
    override = os.environ.get("VOICEMODE_HOOK_BINARY", "").strip()
    if override:
        chosen = Path(override)
        if chosen.is_file() and hook_binary_runs(chosen):
            return chosen
    cache_dir = Path(os.environ.get("VOICEMODE_HOOK_CACHE_DIR", HOOK_CACHE_DIR))
    cache_bin = cache_dir / "voicemode_hook"
    cache_stamp = cache_dir / "voice_mode_version"
    stamped = cache_stamp.read_text(encoding="utf-8").strip() if cache_stamp.is_file() else ""
    if cache_bin.is_file() and stamped == VERSION and hook_binary_runs(cache_bin):
        return cache_bin

    cache_dir.mkdir(parents=True, exist_ok=True)
    if PACKAGED_BINARY.is_file() and hook_binary_runs(PACKAGED_BINARY):
        shutil.copy2(PACKAGED_BINARY, cache_bin)
    elif BUILD_SH.is_file() and shutil.which("sh") and shutil.which("cargo"):
        try:
            subprocess.run(["sh", str(BUILD_SH), str(cache_bin)], check=True)
        except subprocess.CalledProcessError:
            return None
    else:
        return None
    cache_bin.chmod(cache_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if not hook_binary_runs(cache_bin):
        return None
    cache_stamp.write_text(VERSION + "\n", encoding="utf-8")
    return cache_bin


def copy_cached_binary_into_plugin(dest: Path, binary: Path) -> Path:
    bin_dir = dest / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "voicemode_hook"
    shutil.copy2(binary, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def _hook_command(client: str, dest: Path) -> str:
    hook_client = HOOK_CLIENT[client]
    if client == "cursor":
        return f'"$CURSOR_PLUGIN_ROOT/bin/voicemode_hook" --client={hook_client}'
    path = dest / "bin" / "voicemode_hook"
    return f'"{path}" --client={hook_client}'


def plugin_hooks_payload(client: str, dest: Path) -> dict:
    command = _hook_command(client, dest)
    if client == "cursor":
        return {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {
                        "command": command,
                        "timeout": 2,
                        "matcher": "MCP:converse",
                    }
                ]
            },
        }
    if client == "copilot":
        return {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {
                        "type": "command",
                        "command": command,
                        "timeoutSec": 2,
                    }
                ]
            },
        }
    if client == "antigravity":
        return {
            "voicemode-converse": {
                "PreInvocation": [
                    {
                        "type": "command",
                        "command": command,
                    }
                ]
            }
        }
    matcher = "converse|converse_continue|mcp__.*converse"
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": matcher,
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 2,
                        }
                    ],
                }
            ]
        }
    }


def mcp_server_entry(client: str) -> dict:
    command = voicemode_mcp_command()
    name = user_wire_name(client)
    if name == "cursor":
        return {"command": command}
    if name == "copilot":
        return {"tools": ["*"], "type": "local", "command": command, "args": []}
    if name == "antigravity":
        return {"command": command, "args": []}
    return {"type": "stdio", "command": command, "args": []}


def mcp_payload(client: str = "generic") -> dict:
    return {"mcpServers": {"voicemode": mcp_server_entry(client)}}


def cursor_plugin_json() -> dict:
    return {
        "name": "voicemode",
        "displayName": "VoiceMode",
        "version": VERSION,
        "description": "Voice conversations for Cursor: skills, commands, converse hooks, and MCP.",
        "skills": "./skills/",
        "commands": "./commands/",
        "hooks": "./hooks/hooks.json",
        "mcpServers": "./.mcp.json",
    }


def claude_plugin_json() -> dict:
    return {
        "name": "voicemode",
        "version": VERSION,
        "description": "Voice conversations for Claude Code using local speech-to-text and text-to-speech",
        "author": {"name": "IB-QA"},
        "commands": "./commands/",
        "skills": "./skills/",
        "hooks": "./hooks/hooks.json",
    }


def generic_plugin_json(client: str) -> dict:
    return {
        "name": "voicemode",
        "version": VERSION,
        "description": f"VoiceMode plugin for {client}: skills, commands, converse hooks, and MCP.",
        "skills": "./skills/",
        "commands": "./commands/",
        "hooks": "./hooks/hooks.json",
    }


def skill_md() -> str:
    clients = ", ".join(CLIENTS)
    return f"""---
name: voicemode
description: Voice interaction. Use when users mention voice mode, speak, talk, or converse.
---

# VoiceMode

Use the `converse` MCP tool. Pass `message` and `wait_for_response=true` when a reply is expected.

Install this plugin:

```bash
voicemode plugin install --client=CLIENT --converse-hooks
voicemode plugin install --client=all --converse-hooks
```

Clients: {clients}.

The installer writes a plugin folder and merges that client's real
user-level hooks and MCP config (other entries kept). MCP command is
`voicemode`.
"""


def command_md() -> str:
    clients = ", ".join(CLIENTS)
    return f"""---
description: Install the VoiceMode plugin (hooks, skills, bundled MCP) and merge each client's user-level hooks and MCP config.
---

# VoiceMode plugin

```bash
voicemode plugin install --client=CLIENT[,CLIENT...] --converse-hooks
voicemode plugin install --client=all --converse-hooks
```

Clients: {clients}.

ChatGPT web has no agent hook runtime. `--client=chatgpt` installs into the Codex plugin directory (`~/.codex/plugins/voicemode`).
"""


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".before-voicemode")
    if path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json_object(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Cannot merge {path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise click.ClickException(f"Cannot merge {path}: expected a JSON object")
    return data


def merge_mcp_servers(path: Path, servers: dict) -> Path:
    data = _read_json_object(path)
    existing = data.setdefault("mcpServers", {})
    if not isinstance(existing, dict):
        existing = {}
        data["mcpServers"] = existing
    for name, entry in servers.items():
        current = existing.get(name)
        if isinstance(current, dict) and isinstance(entry, dict):
            if "command" in entry:
                current["command"] = entry["command"]
            for key, value in entry.items():
                if key not in current:
                    current[key] = value
        else:
            existing[name] = entry
    _write_json(path, data)
    return path


def merge_named_hooks(path: Path, named: dict) -> Path:
    data = _read_json_object(path)
    data.update(named)
    _write_json(path, data)
    return path


def _entry_command_blob(entry: dict) -> str:
    parts = [
        str(entry.get("command", "")),
        str(entry.get("bash", "")),
        str(entry.get("powershell", "")),
    ]
    nested = entry.get("hooks")
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                parts.append(_entry_command_blob(item))
    return " ".join(parts)


def _is_voicemode_hook_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    return "voicemode_hook" in _entry_command_blob(entry)


def _is_cursor_voicemode_hook(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    command = str(entry.get("command", ""))
    matcher = str(entry.get("matcher", ""))
    return "voicemode_hook" in command and "converse" in matcher.lower()


def _user_hook_command(client: str, dest: Path) -> str:
    hook_client = HOOK_CLIENT[user_wire_name(client)]
    path = dest / "bin" / "voicemode_hook"
    return f'"{path}" --client={hook_client}'


def nested_pretool_entry(command: str) -> dict:
    return {
        "matcher": CLAUDE_CONVERSE_MATCHER,
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 2,
            }
        ],
    }


def merge_nested_pretooluse(path: Path, command: str, *, wrap_hooks: bool) -> Path:
    data = _read_json_object(path)
    if wrap_hooks:
        bucket = data.setdefault("hooks", {})
        if not isinstance(bucket, dict):
            bucket = {}
            data["hooks"] = bucket
    else:
        bucket = data
    events = bucket.get("PreToolUse", [])
    if not isinstance(events, list):
        events = []
    bucket["PreToolUse"] = [e for e in events if not _is_voicemode_hook_entry(e)]
    bucket["PreToolUse"].append(nested_pretool_entry(command))
    _write_json(path, data)
    return path


def ensure_codex_toml_mcp(path: Path, command: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "[mcp_servers.voicemode]" in text:
        return path
    block = f'\n[mcp_servers.voicemode]\nenabled = true\ncommand = "{command}"\n'
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block, encoding="utf-8")
    return path


GUARD_MARKER = "hook stop-guard"


def stop_guard_command(client: str) -> str:
    return f'"{voicemode_mcp_command()}" hook stop-guard --client {client}'


def _is_stop_guard_entry(entry: object) -> bool:
    return isinstance(entry, dict) and GUARD_MARKER in _entry_command_blob(entry)


def merge_cursor_stop_guard(path: Path) -> Path:
    """Add the turn-end guard to Cursor's ``stop`` event. Other entries kept."""
    data = _read_json_object(path) or {"version": 1, "hooks": {}}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    events = hooks.get("stop", [])
    if not isinstance(events, list):
        events = []
    hooks["stop"] = [e for e in events if not _is_stop_guard_entry(e)]
    hooks["stop"].append({"command": stop_guard_command("cursor"), "timeout": 15})
    data.setdefault("version", 1)
    _write_json(path, data)
    return path


def merge_claude_stop_guard(path: Path) -> Path:
    """Add the turn-end guard to Claude Code's ``Stop`` event. Other entries kept."""
    data = _read_json_object(path)
    bucket = data.setdefault("hooks", {})
    if not isinstance(bucket, dict):
        bucket = {}
        data["hooks"] = bucket
    events = bucket.get("Stop", [])
    if not isinstance(events, list):
        events = []
    bucket["Stop"] = [e for e in events if not _is_stop_guard_entry(e)]
    bucket["Stop"].append(
        {
            "hooks": [
                {"type": "command", "command": stop_guard_command("claude"), "timeout": 15}
            ]
        }
    )
    _write_json(path, data)
    return path


def wire_stop_guard(client: str, output: Path | None) -> list[tuple[str, Path]]:
    """Keep agents from ending a turn while the user is still talking."""
    name = user_wire_name(client)
    if name == "cursor":
        path = cursor_user_hooks_path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        return [("stop-guard", merge_cursor_stop_guard(path))]
    if name == "claude":
        return [("stop-guard", merge_claude_stop_guard(claude_user_hooks_path(output)))]
    return []


def wire_antigravity(dest: Path, output: Path | None, converse_hooks: bool) -> tuple[Path, Path | None]:
    cfg = antigravity_config_dir(output)
    cfg.mkdir(parents=True, exist_ok=True)
    mcp_path = merge_mcp_servers(cfg / "mcp_config.json", mcp_payload("antigravity")["mcpServers"])
    hooks_path = None
    if converse_hooks:
        hooks_path = merge_named_hooks(cfg / "hooks.json", plugin_hooks_payload("antigravity", dest))
    return mcp_path, hooks_path


def cursor_user_hook_entry(dest: Path) -> dict:
    binary = dest / "bin" / "voicemode_hook"
    return {
        "command": f'"{binary}" --client=cursor',
        "timeout": 2,
        "matcher": "MCP:converse",
    }


def merge_cursor_user_hooks(path: Path, dest: Path) -> Path:
    data = _read_json_object(path)
    if not data:
        data = {"version": 1, "hooks": {}}
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    events = hooks.get("preToolUse", [])
    if not isinstance(events, list):
        events = []
    hooks["preToolUse"] = [e for e in events if not _is_cursor_voicemode_hook(e)]
    hooks["preToolUse"].append(cursor_user_hook_entry(dest))
    if "version" not in data:
        data["version"] = 1
    _write_json(path, data)
    return path


def copilot_user_hook_payload(dest: Path) -> dict:
    binary = dest / "bin" / "voicemode_hook"
    quoted = f"'{binary}' --client=copilot"
    return {
        "version": 1,
        "hooks": {
            "preToolUse": [
                {
                    "type": "command",
                    "bash": quoted,
                    "powershell": f"& {quoted}",
                    "timeoutSec": 2,
                }
            ]
        },
    }


def register_copilot_plugin(dest: Path) -> bool:
    """Register the plugin folder with GitHub Copilot CLI (`copilot plugin install`).

    Copilot keeps its own plugin registry, so copying a folder into place is not
    enough: it never shows up. Returns False when the CLI is missing or refuses,
    and the caller falls back to the user-level MCP and hook files.
    """
    if os.environ.get("VOICEMODE_COPILOT_SKIP_PLUGIN_REGISTER"):
        return False
    copilot = shutil.which("copilot")
    if not copilot:
        return False
    try:
        # Reinstall so an upgrade replaces the old copy; failure here just means
        # it was not installed yet.
        subprocess.run([copilot, "plugin", "uninstall", "voicemode"],
                       capture_output=True, text=True, timeout=60)
        result = subprocess.run([copilot, "plugin", "install", str(dest)],
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "installed successfully" in (result.stdout or "")


def remove_copilot_user_entries(output: Path | None) -> None:
    """Drop the VoiceMode MCP entry and hook file an earlier install wrote."""
    mcp_path = copilot_user_mcp_path(output)
    try:
        if mcp_path.is_file():
            data = json.loads(mcp_path.read_text())
            servers = data.get("mcpServers")
            if isinstance(servers, dict) and "voicemode" in servers:
                del servers["voicemode"]
                _write_json(mcp_path, data)
        hooks_path = copilot_user_hooks_path(output)
        if hooks_path.is_file():
            hooks_path.unlink()
    except (OSError, ValueError):
        pass


def wire_user_level(
    client: str,
    dest: Path,
    output: Path | None,
    converse_hooks: bool,
) -> list[tuple[str, Path]]:
    """Merge VoiceMode into the files this client actually loads. Other entries kept."""
    name = user_wire_name(client)
    written: list[tuple[str, Path]] = []
    command = voicemode_mcp_command()
    hook_command = _user_hook_command(name, dest)

    if name == "antigravity":
        mcp_path, hooks_path = wire_antigravity(dest, output, converse_hooks)
        written.append(("mcp", mcp_path))
        if hooks_path is not None:
            written.append(("hooks", hooks_path))
        return written

    if name == "cursor":
        mcp_path = merge_mcp_servers(
            cursor_user_mcp_path(output), {"voicemode": mcp_server_entry("cursor")}
        )
        written.append(("mcp", mcp_path))
        if converse_hooks:
            hooks_path = cursor_user_hooks_path(output)
            hooks_path.parent.mkdir(parents=True, exist_ok=True)
            written.append(("hooks", merge_cursor_user_hooks(hooks_path, dest)))
        return written

    if name == "claude":
        mcp_path = merge_mcp_servers(
            claude_user_mcp_path(output), {"voicemode": mcp_server_entry("claude")}
        )
        written.append(("mcp", mcp_path))
        if converse_hooks:
            written.append(
                (
                    "hooks",
                    merge_nested_pretooluse(
                        claude_user_hooks_path(output), hook_command, wrap_hooks=True
                    ),
                )
            )
        return written

    if name == "copilot":
        # Preferred: let Copilot register the plugin itself. It then lists and
        # enables it, and the plugin already carries the MCP server and hook, so
        # writing the user-level files as well would load both twice.
        if register_copilot_plugin(dest):
            remove_copilot_user_entries(output)
            written.append(("plugin", dest))
            return written
        mcp_path = merge_mcp_servers(
            copilot_user_mcp_path(output), {"voicemode": mcp_server_entry("copilot")}
        )
        written.append(("mcp", mcp_path))
        if converse_hooks:
            hooks_path = copilot_user_hooks_path(output)
            _write_json(hooks_path, copilot_user_hook_payload(dest))
            written.append(("hooks", hooks_path))
        return written

    if name == "codex":
        mcp_path = ensure_codex_toml_mcp(codex_user_mcp_path(output), command)
        written.append(("mcp", mcp_path))
        if converse_hooks:
            written.append(
                (
                    "hooks",
                    merge_nested_pretooluse(
                        codex_user_hooks_path(output), hook_command, wrap_hooks=True
                    ),
                )
            )
        return written

    if name == "devin":
        if converse_hooks:
            written.append(
                (
                    "hooks",
                    merge_nested_pretooluse(
                        devin_user_hooks_path(output), hook_command, wrap_hooks=False
                    ),
                )
            )
        return written

    return written


def _copy_agents_templates(dest: Path) -> None:
    skills_src = AGENTS_DIR / "skills"
    if skills_src.is_dir():
        for skill in skills_src.iterdir():
            if skill.is_dir() and (skill / "SKILL.md").is_file():
                target = dest / "skills" / skill.name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(skill, target)
    commands_src = AGENTS_DIR / "commands"
    if commands_src.is_dir():
        cmd_dest = dest / "commands"
        cmd_dest.mkdir(parents=True, exist_ok=True)
        for item in commands_src.iterdir():
            if item.is_file():
                shutil.copy2(item, cmd_dest / item.name)

    skill_path = dest / "skills" / "voicemode" / "SKILL.md"
    if not skill_path.is_file():
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(skill_md(), encoding="utf-8")
    (dest / "commands").mkdir(parents=True, exist_ok=True)
    (dest / "commands" / "voicemode-plugin.md").write_text(command_md(), encoding="utf-8")


def _plugin_readme(client: str, dest: Path) -> str:
    return (
        f"# VoiceMode plugin ({client})\n\n"
        f"Installed to `{dest}`.\n\n"
        "Enable this plugin in the client. MCP starts `voicemode`.\n\n"
        "The installer also merges this client's user-level hooks and MCP "
        "config (other servers and hook events are kept).\n"
    )


def install_plugin(
    client: str,
    *,
    converse_hooks: bool,
    output: Path | None,
    binary: Path | None,
    stop_guard: bool = False,
) -> tuple[Path, list[tuple[str, Path]]]:
    dest = plugin_home(client, output)
    parent = dest.parent
    if not parent.exists():
        app_dir = CLIENT_APP_DIRS[client]
        if output is not None or not app_dir.is_dir():
            raise click.ClickException(
                f"{parent} does not exist. Install {client} first, or create that folder."
            )
        parent.mkdir(parents=True, exist_ok=True)

    dest.mkdir(parents=True, exist_ok=True)
    _copy_agents_templates(dest)
    if binary is not None:
        copy_cached_binary_into_plugin(dest, binary)
    _write_json(dest / ".mcp.json", mcp_payload(client))
    (dest / "README.md").write_text(_plugin_readme(client, dest), encoding="utf-8")

    if client == "cursor":
        _write_json(dest / ".cursor-plugin" / "plugin.json", cursor_plugin_json())
    elif client == "claude":
        _write_json(dest / ".claude-plugin" / "plugin.json", claude_plugin_json())
        _write_json(dest / "plugin.json", claude_plugin_json())
    else:
        _write_json(dest / "plugin.json", generic_plugin_json(client))

    if converse_hooks:
        hooks_payload = plugin_hooks_payload(client, dest)
        _write_json(dest / "hooks" / "hooks.json", hooks_payload)
        if client == "devin":
            _write_json(dest / "hooks" / "hooks.v1.json", hooks_payload.get("hooks", hooks_payload))

    wired = wire_user_level(client, dest, output, converse_hooks)
    if stop_guard:
        wired += wire_stop_guard(client, output)
    return dest, wired


def preview_user_targets(client: str, converse_hooks: bool) -> list[tuple[str, Path]]:
    name = user_wire_name(client)
    items: list[tuple[str, Path]] = [("plugin", plugin_home(client, None))]
    if name == "antigravity":
        cfg = antigravity_config_dir(None)
        items.append(("mcp", cfg / "mcp_config.json"))
        if converse_hooks:
            items.append(("hooks", cfg / "hooks.json"))
        return items
    if name == "cursor":
        items.append(("mcp", cursor_user_mcp_path(None)))
        if converse_hooks:
            items.append(("hooks", cursor_user_hooks_path(None)))
        return items
    if name == "claude":
        items.append(("mcp", claude_user_mcp_path(None)))
        if converse_hooks:
            items.append(("hooks", claude_user_hooks_path(None)))
        return items
    if name == "copilot":
        items.append(("mcp", copilot_user_mcp_path(None)))
        if converse_hooks:
            items.append(("hooks", copilot_user_hooks_path(None)))
        return items
    if name == "codex":
        items.append(("mcp", codex_user_mcp_path(None)))
        if converse_hooks:
            items.append(("hooks", codex_user_hooks_path(None)))
        return items
    if name == "devin" and converse_hooks:
        items.append(("hooks", devin_user_hooks_path(None)))
    return items


def confirm_live_install(clients: list[str], converse_hooks: bool) -> None:
    seen: set[Path] = set()
    click.echo("Will write or merge:")
    for name in clients:
        dest = plugin_home(name, None)
        if dest in seen:
            click.echo(f"  {name}: shares {dest}")
            continue
        seen.add(dest)
        for kind, path in preview_user_targets(name, converse_hooks):
            click.echo(f"  {name} {kind}: {path}")
    if not click.confirm("Continue?"):
        raise click.Abort()


@click.group(help="Install VoiceMode client plugins (hooks, skills, bundled MCP).")
@click.help_option("-h", "--help")
def plugin() -> None:
    pass


@plugin.command(
    "install",
    help=(
        "Write a VoiceMode plugin folder and merge that client's user-level "
        "hooks.json / MCP config (other entries kept). Cursor matcher stays "
        "MCP:converse. ChatGPT shares Codex user files. Devin has no user MCP file."
    ),
)
@click.option(
    "--client",
    required=True,
    help=(
        "cursor, claude, copilot, antigravity, codex, chatgpt, devin. "
        "Comma-separated, or all."
    ),
)
@click.option(
    "--converse-hooks/--no-converse-hooks",
    default=True,
    show_default=True,
    help="Install the converse PreToolUse policy hook inside the plugin.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Override the plugins root (uses <output>/<client>/voicemode).",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip confirmation before writing user-level hooks and MCP files.",
)
@click.help_option("-h", "--help")
def plugin_install(
    client: str, converse_hooks: bool, output: Path | None, yes: bool
) -> None:
    clients = parse_clients(client)
    if output is None and not yes:
        confirm_live_install(clients, converse_hooks)
    # The guard needs only the voicemode command, not the platform hook binary.
    stop_guard = converse_hooks
    binary = ensure_cached_hook_binary() if converse_hooks else None
    if converse_hooks and binary is None:
        click.echo(
            "warning: the converse hook cannot run on this machine (no matching "
            "binary and no cargo to build it). Installing MCP and skills without it."
        )
        converse_hooks = False
    written: list[tuple[str, Path]] = []
    seen_dest: set[Path] = set()
    for name in clients:
        dest = plugin_home(name, output)
        if dest in seen_dest:
            click.echo(f"{name}: shares {dest} (already written)")
            continue
        dest, wired = install_plugin(
            name,
            converse_hooks=converse_hooks,
            output=output,
            binary=binary,
            stop_guard=stop_guard,
        )
        seen_dest.add(dest)
        written.append((name, dest))
        click.echo(f"{name}: {dest}")
        if name == "chatgpt":
            click.echo(
                "  note: ChatGPT web has no hook runtime; this is the Codex plugin folder "
                "and Codex user config."
            )
        for kind, path in wired:
            click.echo(f"  {kind}: {path}")
    if not written:
        raise click.ClickException("No plugins were installed.")
