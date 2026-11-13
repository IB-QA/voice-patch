# ADR 0003: Windows console UTF-8 hardening and portability fixes

- Status: Accepted
- Date: 2026-11-13
- Related: [ADR 0001](0001-windows-local-services.md)

## Context

Running VoiceMode commands on Windows failed in three ways that hid the real problem:

1. **Console encoding.** CLI output contains emoji. On a console using a legacy code page
   such as cp1252, `print` raised `UnicodeEncodeError`, so the user saw a traceback
   instead of the message (and the command often aborted).
2. **click's console writer.** On some setups click's private Windows writer fails on
   stderr with `OSError: Windows error: 6` (invalid handle). Usage errors and
   `ClickException`s turned into tracebacks.
3. **POSIX-only calls.** `os.uname()` and `which` do not exist on Windows. They were used
   in `migration_helpers.py` and `whisper_helpers.py`.

## Decision

1. `voice_mode/cli.py` defines `harden_windows_console()` and calls it at import time. On
   `win32` it:
   - calls `reconfigure(encoding="utf-8", errors="replace")` on `sys.stdout` and
     `sys.stderr`, so unencodable characters are replaced rather than raised;
   - replaces `click._compat._get_windows_console_stream` with a stub returning `None`, so
     click falls back to Python's own (live-handle) `sys.stderr`.

   It is a no-op on other platforms and swallows reconfigure failures.
2. Replace `os.uname().sysname` with `platform.system()` in `migration_helpers.py`.
3. Replace `subprocess.run(["which", ...])` with `shutil.which(...)` in
   `whisper_helpers.py`.
4. Windows branches in `whisper_helpers.py` and `kokoro_helpers.py` locate installs by
   searching `candidate_base_dirs()` (user first, then machine).
5. The Windows `service` helpers decode log files with `errors="replace"`.

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Strip emoji from all CLI output | Large, noisy change; emoji are part of the existing UX on other platforms. |
| Require `PYTHONUTF8=1` or `chcp 65001` | Users will not set it, and failures stay silent. |
| Only catch `UnicodeEncodeError` at the entry point | Loses the message that was being printed. |
| Pin an older click | Avoids neither the encoding issue nor future click changes. |

## Consequences

- Output on legacy code pages may show `?` where the terminal cannot render a glyph; that
  is intentional (`errors="replace"`).
- The click patch touches a private attribute (`_get_windows_console_stream`) and is
  guarded by `hasattr`; if click removes it the patch becomes a no-op and the encoding
  fix still applies.
- Code that must run on Windows has to avoid `os.uname`, `os.getuid` and external `which`.
  Use `platform.system()` and `shutil.which`.
- Tests: `tests/test_windows_console.py`.
