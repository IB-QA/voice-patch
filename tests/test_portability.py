"""Cross-platform portability guards (Windows cp1252 vs POSIX UTF-8)."""
import ast
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "voice_mode"
ALLOWLIST: set = set()


def _source_files():
    for path in PKG.rglob("*.py"):
        if "livekit" in path.relative_to(PKG).parts or "livekit" in path.name:
            continue
        if path.relative_to(PKG).as_posix() in ALLOWLIST:
            continue
        yield path


def _is_binary_mode(call: ast.Call) -> bool:
    mode = None
    if len(call.args) > 1:
        mode = call.args[1]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode = kw.value
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value


def test_text_io_specifies_encoding():
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_text_io = (
                isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text")
            ) or (isinstance(func, ast.Name) and func.id == "open")
            if not is_text_io:
                continue
            if any(kw.arg == "encoding" for kw in node.keywords):
                continue
            if isinstance(func, ast.Name) and _is_binary_mode(node):
                continue
            offenders.append(f"{path.relative_to(PKG)}:{node.lineno}")
    assert not offenders, "text-mode IO without encoding: " + ", ".join(offenders)


def test_file_handlers_use_utf8():
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                if name in ("FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler"):
                    if not any(kw.arg == "encoding" for kw in node.keywords):
                        offenders.append(f"{path.relative_to(PKG)}:{node.lineno}")
    assert not offenders, "log handlers without encoding: " + ", ".join(offenders)


def test_import_emits_no_syntax_warning():
    result = subprocess.run(
        [sys.executable, "-W", "default", "-c", "import voice_mode, pydub.utils"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert "SyntaxWarning" not in result.stderr, result.stderr
