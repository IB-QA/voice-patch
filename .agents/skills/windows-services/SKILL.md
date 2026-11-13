---
name: windows-services
description: Install, diagnose and repair VoiceMode local Whisper and Kokoro services on Windows (Scheduled Tasks, user or machine scope). Use for Windows service install, status, logs, autostart or scope questions.
---

# Windows local services

Whisper (STT, `:2022`, whisper.cpp prebuilt, CUDA 12.4 build on NVIDIA GPUs) and Kokoro
(TTS, `:8880`, CUDA torch on NVIDIA GPUs, else CPU) run as
Windows Scheduled Tasks `VoiceMode-<Svc>`. Details: `docs/architecture/adr/0001-windows-local-services.md`,
`docs/guides/windows-local-services.md`, `docs/architecture/windows-workflows.md`.

## Scopes

| | user (no admin) | machine (admin) |
| - | - | - |
| Data | `~\.voicemode` | `%ProgramData%\VoiceMode` |
| Trigger | at logon | at startup |
| Principal | current user, Limited | SYSTEM, Highest |

Both restart 5 times at 1 minute and have no time limit. Select with
`--scope auto|user|machine` or `VOICEMODE_SERVICE_SCOPE`.

## Workflow

1. Install: `uv tool install --editable C:\wgr\voice-patch`, then
   `voicemode service install whisper --model large-v3-turbo` and
   `voicemode service install kokoro` (`--scope auto` is the default). It is a command
   group: `voicemode service install <svc> --help` lists that service's options (whisper:
   `--model`, `--no-model`, `--use-gpu/--no-gpu`, `--install-dir`, `--version`,
   `--auto-enable`, `--skip-core-ml`, `--skip-deps`, `--force`, `--scope`; kokoro:
   `--device auto|cpu|gpu`, `--install-dir`, `--models-dir`, `--port`, `--no-models`,
   `--version`, `--auto-enable`, `--skip-deps`, `--force`, `--scope`; voicemode:
   `--auto-enable`, `--scope`). Whisper install also activates the model.
2. Diagnose: `voicemode status`, `voicemode service status|logs|health <svc>`,
   `Get-ScheduledTask VoiceMode-*`, logs in `<base>\logs\<svc>\`.
3. Repair: `service restart`, `service install <svc> --force`, or `service uninstall` and
   reinstall in the right scope.
4. Verify: `voicemode status`, then a `converse` call.

## GPU

- Whisper: CUDA 12.4 build if `nvidia-smi` finds a GPU and it starts, else CPU; recorded
  in `bin\.variant`. Kokoro: torch from `cu130` then `cu128`, verified with
  `torch.cuda.is_available()`, else CPU; recorded in `<kokoro>\.device`, override with
  `VOICEMODE_KOKORO_DEVICE`. Intel iGPU/NPU are not used.
- The first whisper request takes about 45 s (CUDA JIT on a new architecture); later
  requests take about 1 s.
- Switch model: `voicemode whisper model large-v3-turbo`.

## DO

- Run `voicemode service install <svc> --help` and pass `--model large-v3-turbo` for Whisper.
- Verify GPU use in the logs (`CUDA0` for whisper, `cuda` for kokoro).
- Pass `encoding="utf-8"` for all text file I/O and guard POSIX-only calls.
- Run MCP from the local exe (`C:\Users\<user>\.local\bin\voicemode.exe`), not `uvx voice-mode`.
- Set `UV_SYSTEM_CERTS=1` for uv on corporate TLS.
- Report machine scope and real reboot/logon autostart as unverified unless you tested them; GPU is verified only on an RTX PRO 500 Blackwell laptop.
- Run `uv run pytest tests/test_windows_services.py tests/test_windows_console.py` after touching Windows code.

## DON'T

- Never `eval`, `Invoke-Expression` or expand `voicemode.env`; it is inert `KEY=VALUE` data.
- Never silently downgrade `machine` to `user`; `ElevationRequired` must surface.
- Never hand-write install commands or scripts; use `voicemode service install <svc>`.
- Never call POSIX-only APIs (`os.getuid`, `pgrep`, `which`) without a guard, or open text files without `encoding="utf-8"` (`tests/test_portability.py`).
- Never treat the first slow GPU whisper request as a hang.
- Never edit version files by hand; use `scripts/release.py`.
- Never change LiveKit behaviour; it is out of scope on Windows.
- Never bind services to anything but `127.0.0.1` by default.
- Never rewrite `uvx voice-mode` in unrelated docs; they stay until publish.
