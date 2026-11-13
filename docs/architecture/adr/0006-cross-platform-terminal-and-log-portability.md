# ADR 0006: Cross-platform terminal/log portability

- Status: Accepted
- Date: 2026-11-13
- Related: [ADR 0003](0003-windows-console-and-portability.md)

## Context

The same `voicemode converse` run looked different on a Mac and on Windows: the Mac showed
INFO/DEBUG startup lines and audio/debug directories, Windows did not, and Windows printed
`SyntaxWarning` noise from pydub. Worse, `converse_continue` crashed on Windows with a
`'charmap' codec can't encode` error. ADR 0003 fixed the first layer; this ADR records the
full scan and the rules that keep it fixed.

Findings:

- The log lines are **not** platform-specific code. `voicemode converse` prints the same
  INFO/DEBUG startup lines on every OS when `VOICEMODE_DEBUG=true` (and
  `VOICEMODE_SAVE_ALL=true` for the audio and debug directories). The Mac showed them
  because of its configuration, not its code.
- `open()`, `read_text()` and `write_text()` without `encoding=` use the locale code page
  on Windows (cp1252). Conversation job files with non-ASCII text failed to write, which
  was the root cause of the `converse_continue` `charmap` crash.
- pydub emits a `SyntaxWarning` at import on newer Python versions.
- A few POSIX-only calls (`os.getuid`, `pgrep`, `:`-splitting of `PATH`) failed or
  misbehaved on Windows.

## Decision

What was scanned: every `open(`, `.read_text(`, `.write_text(` and `subprocess` call in
`voice_mode/`, plus `os.getuid`/`os.uname`/`pgrep`/`which`/`PATH` splitting.

What changed:

1. All text file I/O passes `encoding="utf-8"` (including conversation job files).
2. `voice_mode/__init__.py` makes the console UTF-8 on Windows and filters the pydub
   `SyntaxWarning`.
3. `os.getuid` is guarded; `pgrep` is replaced or skipped on Windows (model switching no
   longer calls it); `PATH` is split with `os.pathsep`.
4. Debug output stays one code path for all OSes, controlled only by configuration.

### Reproducing the debug view

To see on any machine what the Mac showed, set in `~/.voicemode/voicemode.env`:

```
VOICEMODE_DEBUG=true
VOICEMODE_SAVE_ALL=true
```

### Rules going forward

1. **Always** pass `encoding="utf-8"` to `open`, `Path.read_text` and `Path.write_text` for
   text. Binary files use `"rb"`/`"wb"`.
2. **No POSIX-only calls without guards**: `os.getuid`, `os.uname`, `pgrep`, `which`,
   `fork`, `signal.SIGKILL`. Use `platform.system()`, `shutil.which`, `os.pathsep`, or an
   `if sys.platform` branch.
3. Never print or log platform-specific differences; log differences come from config.
4. `tests/test_portability.py` enforces rule 1 (text I/O specifies an encoding, log file
   handlers use UTF-8) and that importing the package emits no `SyntaxWarning`; a
   violation fails the test run. Rule 2 is enforced by review.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Set `PYTHONUTF8=1` for users | Users forget; services and MCP clients start Python without it. |
| Rely on Python 3.15 default UTF-8 mode | Not available on supported versions. |
| Fix call sites ad hoc when bugs appear | The same class of crash kept returning (`charmap`). |
| Add Windows-only debug output to match the Mac | The difference was configuration, not code. |

## Consequences

- New code that opens text files without `encoding` fails `tests/test_portability.py`.
  Unguarded POSIX-only calls are caught in review.
- Output may show `?` for glyphs the console cannot render (ADR 0003).
- Contributors on any OS can reproduce another OS's log view by matching `voicemode.env`.
