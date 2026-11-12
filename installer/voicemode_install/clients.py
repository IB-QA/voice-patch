"""Coding tools a VoiceMode client install can attach hooks to."""

from pathlib import Path


# Home-directory markers. Claude Code and Claude Desktop share ~/.claude.
# ChatGPT's hook install shares the Codex directory, so it is not a separate row.
CLIENT_DIRS = (
    ("cursor", ".cursor"),
    ("claude", ".claude"),
    ("copilot", ".copilot"),
    ("antigravity", ".gemini"),
    ("codex", ".codex"),
    ("devin", ".devin"),
)


def detect_installed_clients(home: Path) -> list[str]:
    """Return client names whose config directory already exists."""
    return [name for name, folder in CLIENT_DIRS if (home / folder).is_dir()]
