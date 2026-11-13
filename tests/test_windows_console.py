"""click's Windows console writer must not be able to hide error messages."""

import sys

import click._compat as click_compat

from voice_mode import cli


def test_not_applied_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli.harden_windows_console() is False


def test_reconfigures_streams_to_utf8_so_emoji_output_cannot_crash(monkeypatch):
    class Stream:
        def __init__(self):
            self.calls = []

        def reconfigure(self, **kwargs):
            self.calls.append(kwargs)

    out, err = Stream(), Stream()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    cli.harden_windows_console()

    assert out.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert err.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_replaces_click_console_writer_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    sentinel = object()
    monkeypatch.setattr(click_compat, "_get_windows_console_stream", sentinel, raising=False)

    assert cli.harden_windows_console() is True
    # click now falls back to sys.stderr instead of its own console writer
    assert click_compat._get_windows_console_stream(sys.stderr, None, None) is None
