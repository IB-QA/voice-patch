"""Terminal presentation for the installer: banner, steps, tables and menus.

Plain ANSI and box-drawing only. Falls back to ASCII glyphs and no colour when
stdout cannot encode unicode, is not a TTY, or NO_COLOR is set.
"""

import os
import sys
from typing import Iterable, Sequence

import click

PRODUCT = "Agent Voice Connect"
TAGLINE = "Voice for your coding agents"
SUPPORTED_AGENTS = (
    "Cursor",
    "Claude Code",
    "GitHub Copilot",
    "Antigravity",
    "Codex",
    "ChatGPT",
    "Devin",
)
CLIENT_LABELS = {
    "cursor": "Cursor",
    "claude": "Claude Code",
    "copilot": "GitHub Copilot",
    "antigravity": "Antigravity",
    "codex": "Codex",
    "chatgpt": "ChatGPT",
    "devin": "Devin",
}

WIDTH = 66

_UNICODE = {"ok": "✓", "fail": "✗", "warn": "!", "run": "…", "skip": "–", "bullet": "•",
            "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│",
            "lt": "├", "rt": "┤"}
_ASCII = {"ok": "[ok]", "fail": "[xx]", "warn": "[!!]", "run": "[..]", "skip": "[--]", "bullet": "*",
          "tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|",
          "lt": "+", "rt": "+"}

_COLORS = {"ok": "green", "fail": "red", "warn": "yellow", "run": "cyan", "skip": "bright_black"}


def configure_streams() -> None:
    """Make stdout/stderr tolerate any character, even on cp1252 consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def use_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    isatty = getattr(sys.stdout, "isatty", None)
    return bool(isatty and isatty())


def use_unicode() -> bool:
    """True only when the terminal is interactive and can encode box/glyph characters."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    isatty = getattr(sys.stdout, "isatty", None)
    if not (isatty and isatty()):
        return False
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "".join(_UNICODE.values()).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def glyph(name: str) -> str:
    return (_UNICODE if use_unicode() else _ASCII)[name]


def paint(text: str, fg: str | None = None, bold: bool = False) -> str:
    if not use_color():
        return text
    return click.style(text, fg=fg, bold=bold)


def status_mark(status: str) -> str:
    """Glyph for ok / fail / warn / run / skip, coloured when allowed."""
    return paint(glyph(status), fg=_COLORS[status], bold=True)


def _box(lines: Sequence[str], title: str | None = None) -> list[str]:
    inner = WIDTH - 2
    h, v = glyph("h"), glyph("v")
    top = glyph("tl") + h * inner + glyph("tr")
    out = [top]
    for line in lines:
        out.append(v + " " + line.ljust(inner - 1)[: inner - 1] + v)
    out.append(glyph("bl") + h * inner + glyph("br"))
    return out


def banner_lines(version: str | None = None) -> list[str]:
    ver = f"  v{version}" if version else ""
    return [
        "",
        f"  {PRODUCT}{ver}",
        f"  {TAGLINE}",
        "",
        "  Works with: " + ", ".join(SUPPORTED_AGENTS[:4]) + ",",
        "              " + ", ".join(SUPPORTED_AGENTS[4:]),
        "",
    ]


def render_banner(version: str | None = None) -> str:
    return "\n".join(_box(banner_lines(version)))


def print_banner(version: str | None = None) -> None:
    click.echo(paint(render_banner(version), fg="cyan", bold=True))


def section(title: str) -> None:
    click.echo()
    click.echo(paint(f"{glyph('h') * 2} {title} " + glyph("h") * max(2, WIDTH - len(title) - 5), fg="cyan", bold=True))


def step(number: int, total: int, title: str, status: str = "run") -> None:
    click.echo(f"{status_mark(status)} {paint(f'Step {number}/{total}', bold=True)}  {title}")


def message(status: str, text: str) -> None:
    click.echo(f"{status_mark(status)} {text}")


def table(rows: Iterable[tuple[str, str]], title: str | None = None) -> str:
    rows = list(rows)
    key_w = max((len(k) for k, _ in rows), default=0)
    v = glyph("v")
    lines = [f"{k.ljust(key_w)} {v} {val}" for k, val in rows]
    if title:
        lines.insert(0, title)
        lines.insert(1, glyph("h") * (key_w + 1) + glyph("h") + glyph("h") * 30)
    return "\n".join("  " + line for line in lines)


def print_table(rows: Iterable[tuple[str, str]], title: str | None = None) -> None:
    click.echo(table(rows, title))


def client_label(name: str) -> str:
    return CLIENT_LABELS.get(name, name)


def render_menu(title: str, options: Sequence[tuple[str, str]], default: str) -> str:
    """Numbered menu text. ``options`` are (label, description); default is shown in brackets."""
    lines = [paint(title, bold=True)]
    for number, (label, desc) in enumerate(options, start=1):
        suffix = f" - {desc}" if desc else ""
        lines.append(f"  {paint(f'{number})', fg='cyan')} {label}{suffix}")
    lines.append(f"  (default: {default})")
    return "\n".join(lines)


def select_one(title: str, options: Sequence[tuple[str, str]], default_index: int = 1) -> int:
    """Ask for one option by number; returns the 1-based index. Enter picks the default."""
    click.echo()
    click.echo(render_menu(title, options, str(default_index)))
    while True:
        answer = str(click.prompt("Choice", default=str(default_index), show_default=False)).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer)
        message("warn", f"Enter a number from 1 to {len(options)}.")


def print_rule() -> None:
    click.echo(paint(glyph("h") * WIDTH, fg="cyan"))
