---
description: Install the VoiceMode plugin (hooks + skills + bundled MCP) and merge each client's user-level hooks and MCP config.
allowed-tools: Bash(voicemode:*)
---

# /voicemode:hooks

```bash
voicemode plugin install --client=CLIENT[,CLIENT...] --converse-hooks
voicemode plugin install --client=all --converse-hooks
```

Without `--output` or `--yes`, the installer lists the user-level files it will merge and waits for confirmation.

Valid clients: `cursor`, `claude`, `copilot`, `antigravity`, `codex`, `chatgpt`, `devin`.

One installer (`voicemode plugin install`) writes a plugin folder and merges that client's real user-level hooks and MCP config (other entries kept). ChatGPT web has no hook runtime; `chatgpt` shares the Codex plugin directory and Codex user files. Devin has no user MCP file.
