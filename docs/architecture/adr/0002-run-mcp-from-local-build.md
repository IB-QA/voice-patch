# ADR 0002: Run the MCP server from the local build (voicemode.exe), not uvx

- Status: Accepted
- Date: 2026-11-13
- Related: [ADR 0001](0001-windows-local-services.md), [ADR 0004](0004-installer-multi-platform-scope.md)

## Context

The upstream documentation tells every MCP client to launch VoiceMode with
`uvx voice-mode`. That always runs the *published* package. This fork carries Windows
local-service support that is not published, so a client launched through `uvx` would
silently run code without those changes: the `service` tool would report that Windows is
unsupported, and `status` would show upstream commands.

`uvx` also resolves and may download the package on each start, which is slow and fails on
networks with TLS inspection unless `UV_SYSTEM_CERTS=1` is set.

## Decision

1. Install this repository as an editable uv tool:

   ```powershell
   uv tool install --editable C:\wgr\voice-patch
   ```

   This writes `C:\Users\<user>\.local\bin\voicemode.exe`.
2. MCP clients launch that executable by **absolute path** with no arguments (the default
   command starts the MCP server over stdio).
3. Code that records or prints a launch command uses `_runtime_command()` (in
   `voice_mode/cli_commands/status.py`) and `voicemode_command()` (installer), which return
   the installed executable and only fall back to `uvx` when no local executable exists.
4. Documentation that still says `uvx voice-mode` is left as is until the fork is
   published; it describes the upstream package.

## Client configuration

Replace `<user>` with your Windows account name. Use doubled backslashes in JSON.

### Claude Code

```powershell
claude mcp add --scope user voicemode -- "C:\Users\<user>\.local\bin\voicemode.exe"
```

### GitHub Copilot CLI

`~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "voicemode": {
      "type": "local",
      "command": "C:\\Users\\<user>\\.local\\bin\\voicemode.exe",
      "args": [],
      "tools": ["*"]
    }
  }
}
```

### VS Code

`.vscode/mcp.json` in a workspace, or the user-level `mcp.json`:

```json
{
  "servers": {
    "voicemode": {
      "type": "stdio",
      "command": "C:\\Users\\<user>\\.local\\bin\\voicemode.exe",
      "args": []
    }
  }
}
```

### Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "C:\\Users\\<user>\\.local\\bin\\voicemode.exe",
      "args": []
    }
  }
}
```

### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "C:\\Users\\<user>\\.local\\bin\\voicemode.exe",
      "args": []
    }
  }
}
```

After editing a config, restart the client (or reconnect the MCP server) so the new
executable is picked up.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| `uvx voice-mode` | Runs the published package, not this fork. |
| `uvx --from C:\wgr\voice-patch voice-mode` | Rebuilds or re-resolves on every start; slow and TLS-sensitive. |
| `python -m voice_mode` with a venv path | Longer, needs the venv path, and the exe is the stable entry point uv maintains. |
| Bare `voicemode` | Depends on `PATH`, which some GUI clients (Claude Desktop, services) do not inherit. |

## Consequences

- The path is absolute and per user. Config files cannot be shared between accounts
  without editing the user name.
- The install is *editable*: the exe points at the working tree, so moving or deleting
  `C:\wgr\voice-patch` breaks every client.
- Upgrades are `git pull` in the repo. Editable installs pick up Python changes
  immediately; run `uv tool install --editable C:\wgr\voice-patch --force` after a change
  to dependencies or entry points, then restart the MCP client.
- Once the fork is published, the documentation can switch back to `uvx`.
