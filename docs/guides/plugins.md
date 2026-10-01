# VoiceMode Plugins

VoiceMode provides plugins for agent clients (Cursor, Claude Code, Codex, Copilot, and others) so voice tools, skills, commands, and converse-policy hooks can ship as a plugin. Enable the plugin in that client. `voicemode plugin install` also **merges** each client's real user-level hooks and MCP config (other servers and hook events are kept). It does not wipe those files.

| Client | Plugin folder | User-level hooks | User-level MCP |
| ------ | ------------- | ---------------- | -------------- |
| Cursor | `~/.cursor/plugins/local/voicemode` | `~/.cursor/hooks.json` (`preToolUse`, matcher `MCP:converse`) | `~/.cursor/mcp.json` |
| Claude Code | `~/.claude/plugins/voicemode` | `~/.claude/settings.json` (`hooks.PreToolUse`) | `~/.claude.json` (`mcpServers`) |
| GitHub Copilot | `~/.copilot/plugins/voicemode` | `~/.copilot/hooks/voicemode-converse.json` | `~/.copilot/mcp-config.json` |
| Antigravity | `~/.gemini/config/plugins/voicemode` | `~/.gemini/config/hooks.json` | `~/.gemini/config/mcp_config.json` |
| Codex | `~/.codex/plugins/voicemode` | `~/.codex/hooks.json` | `~/.codex/config.toml` (`[mcp_servers.voicemode]`) |
| ChatGPT | same Codex plugin folder (web has no hook runtime) | same as Codex | same as Codex |
| Devin | `~/.devin/plugins/voicemode` | `~/.devin/hooks.v1.json` | none (Devin CLI also reads Claude settings; no Devin user MCP file) |

## Installation

```bash
voicemode plugin install --client=cursor --converse-hooks
voicemode plugin install --client=cursor,claude --converse-hooks
voicemode plugin install --client=all --converse-hooks
```

One command generates the client-specific plugin files and merges the user-level paths in the table above. Do not keep a hooks.json per client in the VoiceMode repo.

The plugin parent folder is created when that client is already installed (`~/.cursor`, `~/.claude`, …). `--output` still requires the `<output>/<client>` directory to exist. ChatGPT installs into the Codex directories.

Override a path in `~/.voicemode/voicemode.env`:

```bash
VOICEMODE_PLUGIN_DIR_CURSOR=~/.cursor/plugins/local
VOICEMODE_HOOK_CACHE_DIR=~/.voicemode/services/hooks
```

The hook binary is built into `~/.voicemode/services/hooks/` when missing or when the VoiceMode version changes, then copied into the plugin `bin/`. Unix ARM64/x86_64 for now (not Windows).

Some clients also expose a marketplace. That is optional and client-specific. The supported VoiceMode path is `voicemode plugin install`.

## Prerequisites

VoiceMode services should be installed and running:

```bash
/voicemode:install
```

or:

```bash
uv tool install voice-mode
voicemode service install whisper
voicemode service install kokoro
```

## Slash Commands

Command names depend on the client. Typical VoiceMode commands:

| Command               | Description                        |
| --------------------- | ---------------------------------- |
| `/voicemode:install`  | Install VoiceMode and dependencies |
| `/voicemode:converse` | Start a voice conversation         |
| `/voicemode:status`   | Check service status               |

## MCP Tools

Once the VoiceMode MCP server is enabled in the client:

- `converse` — speak and listen
- `service` — manage voice services

The exact tool name prefix (`MCP:converse`, `mcp__voicemode__converse`, …) depends on the client.

### Converse Tool Parameters

| Parameter             | Default    | Description                      |
| --------------------- | ---------- | -------------------------------- |
| `message`             | (required) | Text to speak                    |
| `wait_for_response`   | true       | Listen after speaking            |
| `listen_duration_max` | 120        | Maximum recording time (seconds) |
| `voice`               | auto       | TTS voice name                   |
| `vad_aggressiveness`  | 3          | Voice detection strictness (0-3) |

## Transport Modes: Local stdio vs Remote HTTP

The VoiceMode package can ship a stdio launcher that selects transport from `VOICEMODE_MCP_URL`:

| Mode                | `VOICEMODE_MCP_URL` | What runs                              |
| ------------------- | ------------------- | -------------------------------------- |
| **Local (default)** | unset               | bundled stdio server                   |
| **Remote**          | set to a serve URL  | stdio↔HTTP bridge to `voicemode serve` |

Set the URL in `~/.voicemode/voicemode.env` or the environment. Do not hand-edit the user's `mcp.json` from `voicemode plugin install`.

### Remote Mode (Plugin-Only)

Install the plugin on a machine without local Whisper/Kokoro, and point MCP at a host that has a microphone and speakers:

```bash
export VOICEMODE_MCP_URL=https://audio-host.example/mcp/<secret>
```

See the [Serve Configuration guide](serve-configuration.md).

### Authentication

Remote mode reuses `voicemode serve` auth:

- Secret in path: `VOICEMODE_MCP_URL=https://host/mcp/<secret>`
- Optional bearer: `VOICEMODE_MCP_TOKEN`
- IP allowlist on the serve side

If a user already configured a `voicemode` MCP server themselves, that explicit config wins over a plugin-bundled entry.

## Hooks

Converse-policy hooks live **inside the plugin**. They run when the plugin is enabled. They are not written into the user's `hooks.json`.

Soundfont / audio-feedback hooks are a separate Claude-oriented receiver and are not required for the converse policy binary.

## Troubleshooting

```bash
voicemode service status whisper
voicemode service status kokoro
voicemode service logs whisper
voicemode service logs kokoro
```

### No Audio Output

1. System audio works
2. Kokoro is running
3. FFmpeg is installed: `which ffmpeg`

### Speech Not Recognized

1. Whisper is running
2. Microphone permission for the agent client / terminal
3. Adjust VAD if needed

## Configuration

`~/.voicemode/voicemode.env`:

```bash
VOICEMODE_TTS_VOICE=nova
VOICEMODE_WHISPER_MODEL=base
voicemode config edit
```

## Resources

- [GitHub Repository](https://github.com/IB-QA/voice-patchvoicemode)
