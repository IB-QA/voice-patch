---
description: Install, diagnose and repair VoiceMode local services on Windows
allowed-tools: Bash(voicemode:*), Bash(uv:*), Bash(powershell:*), Bash(Get-ScheduledTask:*)
---

# /voicemode:windows-services

Install, diagnose and repair local Whisper (STT, port 2022) and Kokoro (TTS, port 8880) on
Windows. They run as Scheduled Tasks named `VoiceMode-<Svc>`. For the full rules load the
`windows-services` skill.

## Install

```powershell
$env:UV_SYSTEM_CERTS = "1"
uv tool install --editable C:\wgr\voice-patch
voicemode service install whisper --model large-v3-turbo --scope auto
voicemode service install kokoro --device auto --scope auto
```

`auto` means machine scope when elevated, otherwise user scope. Never switch scope for the
user on error. `voicemode service install` is a group: run
`voicemode service install <svc> --help` for that service's options (whisper: `--model`,
`--no-model`, `--use-gpu/--no-gpu`, `--install-dir`, `--version`, `--auto-enable`,
`--skip-core-ml`, `--skip-deps`, `--force`, `--scope`; kokoro: `--device auto|cpu|gpu`,
`--install-dir`, `--models-dir`, `--port`, `--no-models`, `--version`, `--auto-enable`,
`--skip-deps`, `--force`, `--scope`; voicemode: `--auto-enable`, `--scope`).

## GPU

NVIDIA GPU: whisper uses the CUDA 12.4 build (`bin\.variant`), kokoro uses CUDA torch
(`<kokoro>\.device`, override `VOICEMODE_KOKORO_DEVICE`); both fall back to CPU. Verify in
logs (`CUDA0` for whisper, `cuda` for kokoro). The first whisper request takes about 45 s
(CUDA JIT); that is expected. Switch model: `voicemode whisper model large-v3-turbo`.
Intel iGPU/NPU are not used.

## Rules

- DO run `voicemode service install <svc> --help` before choosing options.
- DON'T hand-write install commands or scripts; use the CLI.
- DO pass `--model large-v3-turbo` for Whisper.
- DO verify GPU use via logs, not assumptions.
- DON'T treat the first slow GPU request as a hang.

## Diagnose

```powershell
voicemode status
voicemode service status whisper
voicemode service logs whisper --lines 100
Get-ScheduledTask VoiceMode-*
```

Logs: `<base>\logs\<service>\` where `<base>` is `~\.voicemode` or `%ProgramData%\VoiceMode`.

## Repair

| Problem | Action |
| ------- | ------ |
| Service down | `voicemode service restart <svc>` then read logs |
| Files damaged | `voicemode service install <svc> --force` |
| Wrong scope | `voicemode service uninstall <svc>`, reinstall with the right `--scope` |
| TLS errors | set `UV_SYSTEM_CERTS=1` and retry |
| ffmpeg missing | `winget install Gyan.FFmpeg`, reinstall whisper |
| Client runs old code | point its config at `C:\Users\<user>\.local\bin\voicemode.exe` |

Docs: `docs/guides/windows-local-services.md`, `docs/architecture/adr/`.
