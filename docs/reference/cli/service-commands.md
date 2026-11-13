# Service Management Commands

VoiceMode provides one service lifecycle for Whisper, Kokoro, mlx-audio, the
VoiceMode HTTP server, and the self-hosted LiveKit services.

## Usage

### Backward Compatibility

The default behavior is preserved:
```bash
voicemode              # Starts MCP server (existing behavior)
```

### Service Management

Use the unified command form:

```bash
voicemode service status [SERVICE]
voicemode service start SERVICE
voicemode service stop SERVICE
voicemode service restart SERVICE
voicemode service enable SERVICE
voicemode service disable SERVICE
voicemode service logs SERVICE [-n LINES]
voicemode service install SERVICE        # whisper, kokoro, voicemode, mlx-audio, livekit
voicemode service install SERVICE --help # options for that service
voicemode service uninstall SERVICE
```

`voicemode service install` is a group; each service has its own options
(`whisper`: `--model`, `--no-model`, `--use-gpu/--no-gpu`, `--install-dir`, `--version`,
`--auto-enable`, `--skip-core-ml`, `--skip-deps`, `--force`, `--scope`; `kokoro`:
`--device auto|cpu|gpu`, `--install-dir`, `--models-dir`, `--port`, `--no-models`,
`--version`, `--auto-enable`, `--skip-deps`, `--force`, `--scope`; `voicemode`:
`--auto-enable`, `--scope`; `mlx-audio`: `--port`, `--bind-lan`, `--auto-enable`,
`--force`). Run `voicemode service install SERVICE --help` for details. The Whisper model
chosen at install is also activated. On Windows, see the
[local services guide](../../guides/windows-local-services.md) for GPU variants.

The older top-level Kokoro and Whisper groups shown below remain available for
backward compatibility.

#### Kokoro TTS Service
```bash
voicemode kokoro status           # Show service status and resource usage
voicemode kokoro start            # Start Kokoro service
voicemode kokoro stop             # Stop Kokoro service  
voicemode kokoro restart          # Restart Kokoro service
voicemode kokoro enable           # Enable service at boot/login
voicemode kokoro disable          # Disable service from boot/login
voicemode kokoro logs             # View service logs (default: 50 lines)
voicemode kokoro logs --lines 100 # View last 100 log lines
voicemode kokoro health           # Check health endpoint
voicemode kokoro update-service-files # Update service files to latest
```

#### Whisper STT Service
```bash
voicemode whisper status          # Show service status and resource usage
voicemode whisper start           # Start Whisper service
voicemode whisper stop            # Stop Whisper service
voicemode whisper restart         # Restart Whisper service  
voicemode whisper enable          # Enable service at boot/login
voicemode whisper disable         # Disable service from boot/login
voicemode whisper logs            # View service logs (default: 50 lines)
voicemode whisper logs --lines 100 # View last 100 log lines
voicemode whisper health          # Check health endpoint
voicemode whisper update-service-files # Update service files to latest
```

#### LiveKit SFU and browser gateway

Installing `livekit` creates both the loopback SFU (`livekit`) and loopback
browser gateway (`livekit-web`). Manage their processes separately:

```bash
voicemode service install livekit
voicemode service status livekit
voicemode service status livekit-web
voicemode service start livekit
voicemode service start livekit-web
voicemode service logs livekit -n 100
voicemode service logs livekit-web -n 100
voicemode service enable livekit
voicemode service enable livekit-web
voicemode service uninstall livekit
```

`voicemode service install livekit --rotate-credentials` rotates the LiveKit
API key and secret. `voicemode service uninstall livekit --remove-all-data`
also removes LiveKit logs. See the
[LiveKit setup guide](../../guides/livekit-setup.md) before changing network
settings; the supported managed deployment is loopback-only.

## Examples

### Quick Status Check
```bash
$ voicemode kokoro status
✅ Kokoro is running
   PID: 12345
   Port: 8880
   CPU: 0.1%
   Memory: 8.9 MB
   Uptime: 2h 15m 30s
   Service files: v1.1.1 (latest)
```

### Starting Services
```bash
$ voicemode whisper start
✅ Whisper started successfully (PID: 54321)

$ voicemode kokoro start  
✅ Kokoro started
```

### Health Checks
```bash
$ voicemode kokoro health
✅ Kokoro is responding
   Status: healthy
   Uptime: 2h 15m 30s

$ voicemode whisper health
❌ Whisper not responding on port 2022
```

### Service Management
```bash
$ voicemode kokoro enable
✅ Kokoro service enabled. It will start automatically at login.
Plist: /Users/user/Library/LaunchAgents/com.voicemode.kokoro.plist

$ voicemode whisper disable
✅ Whisper service disabled and removed
```

### Viewing Logs
```bash
$ voicemode kokoro logs --lines 20
=== Last 20 log entries for kokoro ===
[2025-08-11 15:30:42] Starting Kokoro FastAPI server...
[2025-08-11 15:30:43] Server listening on 0.0.0.0:8880
...
```

## Cross-Platform Support

Commands work on both macOS and Linux:
- **macOS**: Uses launchctl for service management
- **Linux**: Uses systemctl for service management  
- **Fallback**: Direct process control when service managers not available


## Benefits

1. **No shell setup required** - Commands work immediately after installing voicemode
2. **Consistent interface** - Same commands on all platforms
3. **Better help text** - Built-in help with `--help`
4. **Standardized options** - Consistent flags like `--lines`
5. **No MCP overhead** - Service commands don't start the MCP server
6. **Future-proof** - Easy to add new service management features
