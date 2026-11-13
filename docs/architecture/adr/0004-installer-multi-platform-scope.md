# ADR 0004: Installer (voice-mode-install) is multi-platform and picks the scope from privileges

- Status: Accepted
- Date: 2026-11-13
- Related: [ADR 0001](0001-windows-local-services.md), [ADR 0002](0002-run-mcp-from-local-build.md)

## Context

`voice-mode-install` (package `installer/voicemode_install`) used to treat native Windows
as a client: it set `skip_services = True` and `should_recommend_local_services()`
returned `False`. After [ADR 0001](0001-windows-local-services.md) the CLI can install
services on Windows, so the installer has to offer them and choose a scope without asking
the user to understand scopes.

## Decision

1. The installer no longer skips services on Windows, and
   `HardwareInfo.should_recommend_local_services()` applies the same hardware rules on
   every platform.
2. `is_windows_admin()` (installer) detects elevation with `IsUserAnAdmin`; it is always
   `False` off Windows.
3. On Windows the installer passes `--scope machine` when elevated and `--scope user`
   otherwise to `voicemode service install whisper|kokoro`, and tells the user which was
   chosen and when the services start (boot or logon).
4. The installer calls the CLI through `voicemode_command()`, the absolute path of the
   `voicemode` executable inside the uv tool directory, because that folder may not be on
   `PATH` in the installing shell.
5. Finishing hints on Windows say `voicemode status` and show the MCP client command using
   the installed executable ([ADR 0002](0002-run-mcp-from-local-build.md)).
6. Linux and macOS behaviour is unchanged.

## Platform matrix

| Platform | Service manager | Scope today | Admin-aware installer | Status |
|---|---|---|---|---|
| Windows | Task Scheduler | `user` (logon) or `machine` (boot) | Yes, passes `--scope` | user scope verified; machine scope unverified |
| macOS | launchd (`~/Library/LaunchAgents`) | per user | No | existing behaviour |
| Linux | `systemd --user` | per user | No | existing behaviour |
| WSL | systemd --user if enabled | per user | No | existing behaviour; extra audio setup may be needed |

## Alternatives considered

| Alternative | Why it was rejected |
|---|---|
| Ask the user to choose a scope interactively | Most users cannot answer it; privilege already decides it. |
| Always pass `--scope auto` | Equivalent today, but the explicit value lets the installer print the outcome and keeps behaviour stable if the CLI default ever changes. |
| Self-elevate (UAC prompt) | Surprising, unattended runs hang, and may be blocked by policy. The user chooses by how they start the shell. |
| Separate installer per OS | More code to maintain and diverging behaviour. |

## Consequences

- A user who wants machine scope must start the installer from an elevated shell. A user
  without admin gets user scope and never sees an error.
- Reinstalling from a different privilege level can leave a service in the other scope;
  `service uninstall` finds either scope, so remove it first if you switch.

## Future work

- A POSIX system-wide scope: systemd system units (`/etc/systemd/system`, data under
  `/var/lib/voicemode`) and launchd daemons (`/Library/LaunchDaemons`), selected with the
  same `--scope auto|user|machine` flag and the same no-silent-downgrade rule. Not
  implemented or verified.
- GPU-enabled Kokoro and whisper.cpp builds on Windows.
- Verify machine scope and boot/logon autostart on a real elevated machine.
