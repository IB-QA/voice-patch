# Architecture Decision Records

Each ADR records one decision, why it was made and what it costs. Copy
[template.md](template.md) to add a new one and number it sequentially.

| ADR | Title | Status | Date | Supersedes / related |
|---|---|---|---|---|
| [0001](0001-windows-local-services.md) | Windows hosts local Whisper and Kokoro, scoped by privilege | Accepted | 2026-11-13 | Supersedes the "Windows is a client only" decision; related 0002, 0003, 0004 |
| [0002](0002-run-mcp-from-local-build.md) | Run the MCP server from the local build (voicemode.exe), not uvx | Accepted | 2026-11-13 | Related 0001, 0004 |
| [0003](0003-windows-console-and-portability.md) | Windows console UTF-8 hardening and portability fixes | Accepted | 2026-11-13 | Related 0001 |
| [0004](0004-installer-multi-platform-scope.md) | Installer is multi-platform and picks the scope from privileges | Accepted | 2026-11-13 | Related 0001, 0002 |
| [0005](0005-unified-service-install-cli-and-gpu-variants.md) | Unified service install CLI and GPU variants | Accepted | 2026-11-13 | Related 0001, 0004 |
| [0006](0006-cross-platform-terminal-and-log-portability.md) | Cross-platform terminal/log portability | Accepted | 2026-11-13 | Extends 0003 |
Statuses: Proposed, Accepted, Deprecated, Superseded by ADR NNNN.

Related reading: [Windows local services guide](../../guides/windows-local-services.md),
[Windows workflows](../windows-workflows.md).
