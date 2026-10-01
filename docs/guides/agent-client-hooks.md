# Agent client hooks

VoiceMode ships two hook families:

1. **Converse PreToolUse rewrite** — bash+jq, fail-open. Forces `wait_for_response` when enabled and strips agent-supplied `listen_duration_max`.
2. **Soundfont receiver** (`voicemode-hook-receiver.sh`) — bash-only audio feedback. Claude Code / Claude Code CLI today.

Config (environment or `~/.voicemode/voicemode.env`, last assignment wins):

| Variable | Default | Effect |
| --- | --- | --- |
| `VOICEMODE_FORCE_WAIT_FOR_RESPONSE` (alias `FORCE_WAIT_FOR_RESPONSE`) | `true` | Set `wait_for_response: true` on `converse` / `converse_continue` |
| `VOICEMODE_STRIP_LISTEN_DURATION_MAX` | `true` | Remove `listen_duration_max` so the server default applies |
| `VOICEMODE_HOOK_CLIENT` | auto | Override client output schema (`claude`, `codex`, `cursor`, `copilot`, `devin`, `antigravity`) |

Disable a policy with `false` / `0` / `off`.

## Plugin install (user-level merge)

```bash
voicemode plugin install --client=cursor,claude --converse-hooks
voicemode plugin install --client=all --converse-hooks
```

One installer (`voicemode plugin install` in `voice_mode/cli_commands/plugin.py`)
writes a plugin folder per client **and** merges that product's real user-level
hooks and MCP config. Other servers and hook events are kept. Agents should
run the installer rather than editing those files by hand.

Do not commit per-client `hooks.json` files in this repo.

## Platform map

| Client | Surfaces | Rewrite converse args? | Wiring in this repo | Notes |
| --- | --- | --- | --- | --- |
| Claude Code / Claude Code CLI | IDE + CLI | Yes — `hookSpecificOutput.updatedInput` | merges `~/.claude/settings.json` and `~/.claude.json` | Matcher `converse\|converse_continue\|mcp__.*converse`. Plugin also plays soundfonts. |
| Claude Desktop | Desktop app | No native PreToolUse | — | MCP only. Policy cannot be enforced by hooks. |
| Codex / Codex CLI | ChatGPT Codex + CLI | Yes — same Claude-shaped `updatedInput` when paired with `allow` | merges `~/.codex/hooks.json` and `[mcp_servers.voicemode]` in `~/.codex/config.toml` | Trust the hook in `/hooks` before it runs. |
| ChatGPT (web app, not Codex) | chatgpt.com | No | shares Codex user files | No agent hook runtime. |
| Cursor IDE / Cursor CLI | IDE + CLI | Yes — `updated_input` | merges `~/.cursor/hooks.json` and `~/.cursor/mcp.json` | Matcher stays `MCP:converse`. |
| GitHub Copilot CLI | CLI + cloud agent | Yes — `modifiedArgs` | writes `~/.copilot/hooks/voicemode-converse.json` and merges `~/.copilot/mcp-config.json` | Command `preToolUse` is **fail-closed** on non-zero exit. The wrapper always exits 0. |
| GitHub Copilot Desktop | Desktop | Partial | same Copilot plugin folder | Confirm in the product's Hooks UI; do not assume CLI parity. |
| Antigravity CLI | `agy` | PreInvocation command (allow/deny; no arg rewrite) | plugin at `~/.gemini/config/plugins/voicemode`; merges `~/.gemini/config/mcp_config.json` + `hooks.json` | Antigravity does not load `~/.antigravity/plugins`. |
| Antigravity IDE | IDE / 2.0 desktop | Unreliable | same files | Treat as unsupported for converse policy. |
| Devin CLI | CLI | Yes — Claude-compatible `updatedInput` | merges `~/.devin/hooks.v1.json`; Devin also reads `.claude/settings.json` | Do not invent a Devin IDE MCP path. |
| Devin IDE | IDE | Unknown / CLI-oriented | — | Use CLI hooks; do not invent an IDE-only format. |
| Zed IDE | IDE | **No** | — | Agent lifecycle hooks are proposals, not a rewrite API. MCP still works. |

## Files

| Path | Role |
| --- | --- |
| `voice_mode/data/hooks/converse-pre-tool-use.sh` | Fast stdin gate + jq rewrite |
| `voice_mode/data/hooks/voicemode-hook-receiver.sh` | Soundfonts (Claude events) |
| `voice_mode/data/hooks/*.json` | Claude plugin hook fragments |

The rewrite hook prints **nothing** unless it changed arguments, so it does not auto-approve unrelated tools.
