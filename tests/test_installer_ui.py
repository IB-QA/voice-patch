"""Installer terminal UI: neutral branding and ASCII fallback."""

import io
import sys
from pathlib import Path

from click.testing import CliRunner

INSTALLER_ROOT = Path(__file__).resolve().parents[1] / "installer"
sys.path.insert(0, str(INSTALLER_ROOT))

from voicemode_install import ui
from voicemode_install.cli import choose_clients, main


class _FakeStdout(io.StringIO):
    def __init__(self, encoding: str, tty: bool):
        super().__init__()
        self._encoding = encoding
        self._tty = tty

    @property
    def encoding(self):
        return self._encoding

    def isatty(self):
        return self._tty


def test_banner_is_neutral_and_branded():
    banner = ui.render_banner("1.0.0")

    assert "Agent Voice Connect" in banner
    assert "Claude" not in banner.replace("Claude Code", "")
    for agent in ("Cursor", "GitHub Copilot", "Antigravity", "Codex", "ChatGPT", "Devin"):
        assert agent in banner


def test_ascii_glyphs_on_cp1252_console(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeStdout("cp1252", True))

    assert ui.use_unicode() is False
    assert ui.glyph("ok") == "[ok]"
    ui.render_banner().encode("cp1252")


def test_ascii_glyphs_when_no_color_or_not_a_tty(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _FakeStdout("utf-8", True))
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui.use_unicode() is False and ui.use_color() is False

    monkeypatch.delenv("NO_COLOR")
    assert ui.use_unicode() is True
    monkeypatch.setattr(sys, "stdout", _FakeStdout("utf-8", False))
    assert ui.use_unicode() is False


def test_choose_clients_menu_uses_neutral_labels(monkeypatch):
    import click

    @click.command()
    def cmd():
        sys.stdin.isatty = lambda: True
        click.echo(str(choose_clients(["claude", "cursor"])))

    result = CliRunner().invoke(cmd, input="2\n")

    assert "Claude Code" in result.output
    assert "['cursor']" in result.output


def test_dry_run_output_has_no_crash_and_new_brand():
    result = CliRunner().invoke(main, ["--dry-run", "--yes", "--skip-services", "--clients", "none"])

    assert result.exit_code == 0, result.output
    assert "Agent Voice Connect" in result.output
    assert "VoiceMode Installer" not in result.output
