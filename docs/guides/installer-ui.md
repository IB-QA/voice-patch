# Installer terminal UI

`uvx voice-mode-install` presents itself as **Agent Voice Connect** ("Voice for your coding agents") and lists its supported agents neutrally: Cursor, Claude Code, GitHub Copilot, Antigravity, Codex, ChatGPT and Devin.

## Layout

- A header panel with the product name, version and supported agents.
- Sections for system, dependencies, install and optional local services (Whisper/Kokoro).
- A system summary table (platform, CPU cores, memory, and on Windows the install scope: machine-wide when elevated, otherwise current user).
- A numbered agent menu. Enter picks the default, `none`; type numbers (`1,3`), `all` or `none`.
- A closing summary with next steps, for example `voicemode plugin install --client=all --converse-hooks`.

## Fallbacks

Status marks are `✓ ✗ ! …` on a UTF-8 terminal. They become `[ok] [xx] [!!] [..]` with ASCII box lines when `NO_COLOR` is set, stdout is not a TTY, or the console encoding (for example Windows cp1252) cannot encode them. Colour is also disabled in those cases. The installer reconfigures stdout/stderr to UTF-8 with `errors="replace"` at start so it never crashes on output.

All flags (`--yes`, `--dry-run`, `--skip-services`, `--clients`, `--model`) are unchanged.
