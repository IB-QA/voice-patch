---
name: voicemode-hooks
description: Install the VoiceMode plugin for a client. Never write mcp.json or the user's hooks.json. Use voicemode plugin install.
---

# VoiceMode plugin install

```bash
voicemode plugin install --client=cursor --converse-hooks
voicemode plugin install --client=cursor,claude --converse-hooks
voicemode plugin install --client=all --converse-hooks
```

Clients: `cursor`, `claude`, `copilot`, `antigravity`, `codex`, `chatgpt`, `devin`.

Agents must not hand-edit a client's user MCP or hooks files. Run `voicemode plugin install`. The installer merges those files (other servers and hook events are kept) at the paths each product actually loads:

- Cursor: `~/.cursor/hooks.json`, `~/.cursor/mcp.json`
- Claude Code: `~/.claude/settings.json`, `~/.claude.json`
- Copilot: `~/.copilot/hooks/voicemode-converse.json`, `~/.copilot/mcp-config.json`
- Antigravity: `~/.gemini/config/hooks.json`, `~/.gemini/config/mcp_config.json`
- Codex / ChatGPT: `~/.codex/hooks.json`, `~/.codex/config.toml`
- Devin: `~/.devin/hooks.v1.json` (no Devin user MCP file)
