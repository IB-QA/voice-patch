# Self-hosted LiveKit browser rooms

VoiceMode's historical LiveKit room transport is restored in this private fork
as an optional, self-hosted feature. It is separate from the removed hosted
VoiceMode Connect/Auth0 product: there is no hosted account, login, or routing
service in this workflow.

The current implementation is intentionally local:

1. A LiveKit SFU listens on loopback (`127.0.0.1:7880`).
2. A loopback browser gateway (`127.0.0.1:7890`) serves the packaged client,
   authenticates it, creates a private room, and mints a short-lived room token.
3. The browser joins that room and publishes microphone audio when you enable
   it.
4. An explicit `converse(..., transport="livekit")` call joins the same room,
   publishes TTS audio, and optionally returns the first final transcript.

Local microphone transport remains the default. VoiceMode does not
automatically route or fall back to LiveKit.

## Prerequisites

- macOS or Linux. The managed installer does not support Windows.
- VoiceMode with the optional LiveKit SDK dependencies. From a source checkout:

  ```bash
  uv sync --extra livekit
  ```

- Working OpenAI-compatible TTS and STT endpoints. Local Whisper and Kokoro can
  provide these; cloud endpoints require `OPENAI_API_KEY`.
- macOS: Homebrew. The installer installs the `livekit` formula and records
  the `livekit-server` version Homebrew actually provides.
- Linux: x86-64/amd64 or arm64/aarch64. The installer downloads the pinned
  LiveKit Server archive and verifies its embedded SHA-256 checksum.
- A browser with microphone permission.

## Install securely

```bash
voicemode service install livekit
```

The installer:

- configures the SFU to bind only to `127.0.0.1`;
- generates random API credentials and a separate browser bearer;
- stores the SFU config, metadata, and generated start scripts under
  `~/.voicemode/services/livekit/` with restrictive permissions;
- writes the required variables to `~/.voicemode/voicemode.env` with mode
  `0600`;
- creates both `livekit` and `livekit-web` launchd agents on macOS or systemd
  user services on Linux;
- enables both services by default when
  `VOICEMODE_SERVICE_AUTO_ENABLE=true` (the default).

Reinstalling preserves existing API credentials and the browser bearer.
`--rotate-credentials` replaces the API key and API secret; it does not rotate
an existing browser bearer.

```bash
voicemode service install livekit --rotate-credentials
```

Do not commit or print `~/.voicemode/voicemode.env` or
`~/.voicemode/services/livekit/livekit.yaml`. The API secret can administer
rooms and mint participant tokens. The browser bearer can ask the local gateway
to create a room and mint a browser participant token.

## Foreground workflow without launchd/systemd

To install the files without loading managed services:

```bash
VOICEMODE_SERVICE_AUTO_ENABLE=false voicemode service install livekit
```

Run these in two terminals so logs stay in the foreground:

```bash
~/.voicemode/services/livekit/bin/start-livekit-server.sh
```

```bash
~/.voicemode/services/livekit/bin/start-livekit-browser.sh
```

The browser script loads `~/.voicemode/voicemode.env`. If you use a different
shell environment, export the same variables before running
`python -m voice_mode.livekit.browser_app`.

## Managed service workflow

The installer normally starts both services. Manage the SFU and gateway
separately:

```bash
voicemode service status livekit
voicemode service status livekit-web

voicemode service start livekit
voicemode service start livekit-web

voicemode service restart livekit
voicemode service restart livekit-web

voicemode service stop livekit-web
voicemode service stop livekit
```

Use `enable` or `disable` for login/boot startup:

```bash
voicemode service enable livekit
voicemode service enable livekit-web
voicemode service disable livekit-web
voicemode service disable livekit
```

## Native join (no browser)

After the SFU is running, VoiceMode can join as the human itself: local microphone published into the room, subscribed audio played on local speakers.

```bash
voicemode livekit join
```

Default room name: `voicemode-native` (created if missing). Optional `--room <name>`. While this process is joined, `converse(..., transport="livekit")` uses that room when `room_name` is omitted.

The packaged browser client remains optional for debugging.

## Open the browser and connect

Start the SFU and gateway, then run:

```bash
voicemode livekit browser open
```

This opens `http://127.0.0.1:7890/` with the browser bearer in the URL
**fragment**, not the query string. The packaged client immediately removes the
fragment from browser history. On the first **Connect** click it sends the
bearer in an `Authorization` header to the loopback gateway and clears its
in-memory copy. The gateway creates a fresh prefixed room and returns a
short-lived, exact-room participant token.

In the page:

1. Choose **Connect**.
2. Choose **Turn on microphone**.
3. Grant microphone permission.

The microphone is not requested or published until step 2. The page subscribes
to remote agent audio and displays final transcription events.

To serve the browser in a foreground terminal without the generated script:

```bash
voicemode livekit browser serve
```

## Find the room

List rooms after the browser connects:

```bash
voicemode livekit rooms list
```

Copy the exact generated room name (for example, one beginning with
`voicemode-browser-`). If exactly one room matches the configured prefix,
`converse` may resolve it when `--room`/`room_name` is omitted. Supplying the
exact name is safer and required when multiple eligible rooms exist.

The opt-in MCP tool can also list or resolve rooms:

```text
livekit_rooms()
livekit_rooms(room_name="<exact-room-name>")
```

`livekit_rooms`, `livekit_install`, and `livekit_uninstall` are not in the
default minimal MCP tool set. Add the needed names to
`VOICEMODE_TOOLS_ENABLED`, or use the CLI. The default `service` MCP tool can
manage `livekit` and `livekit_web`.

## Converse through the room

CLI, listening for the browser participant's first final response:

```bash
voicemode converse "What should we work on?" \
  --transport livekit \
  --room "<exact-room-name>"
```

Speak without waiting for a response:

```bash
voicemode converse "The build finished." \
  --transport livekit \
  --room "<exact-room-name>" \
  --skip-stt
```

Equivalent MCP calls:

```text
converse(
  message="What should we work on?",
  transport="livekit",
  room_name="<exact-room-name>",
  wait_for_response=true
)
```

```text
converse(
  message="The build finished.",
  transport="livekit",
  room_name="<exact-room-name>",
  wait_for_response=false
)
```

Each call creates a temporary agent participant, speaks one scalar message,
optionally waits up to `listen_duration_max` for the first final transcript,
then disconnects and cleans up.

## Environment variables

VoiceMode-specific names take precedence over the compatible `LIVEKIT_*`
fallback names.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VOICEMODE_LIVEKIT_URL` | `ws://127.0.0.1:7880` | SFU WebSocket/control URL |
| `VOICEMODE_LIVEKIT_API_KEY` | none | Server API key; sensitive credential |
| `VOICEMODE_LIVEKIT_API_SECRET` | none | Server API secret; highly sensitive |
| `VOICEMODE_LIVEKIT_ROOM_PREFIX` | `voicemode-` | Eligible room prefix and browser-room prefix |
| `VOICEMODE_LIVEKIT_BROWSER_HOST` | `127.0.0.1` | Browser gateway bind host; loopback only |
| `VOICEMODE_LIVEKIT_BROWSER_PORT` | `7890` | Browser gateway port |
| `VOICEMODE_LIVEKIT_BROWSER_ORIGIN` | derived from host/port | Required exact browser origin |
| `VOICEMODE_LIVEKIT_BROWSER_TOKEN` | none | Sensitive bearer for gateway session creation |

Compatible fallbacks are `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`, and `LIVEKIT_ROOM_PREFIX`. There are no implemented
`LIVEKIT_PORT`, `VOICEMODE_LIVEKIT_AUTO_CREATE`, or automatic transport
selection settings.

Plain `ws://`/`http://` SFU URLs are accepted only for loopback hosts. Remote
hosts require `wss://`/`https://`. The browser host itself is rejected unless
it is loopback, and `VOICEMODE_LIVEKIT_BROWSER_ORIGIN` must exactly match the
configured host and port.

## Security model

- The managed SFU and gateway are loopback-only.
- The installer does not use LiveKit development mode or fixed credentials.
- Browser session creation requires exact Host and Origin headers plus a
  constant-time bearer comparison. Failed authentication is rate-limited.
- Session responses are `no-store`; the page uses restrictive CSP, framing,
  referrer, and content-type headers.
- Browser and agent participant tokens are restricted to one exact room,
  permit publish/subscribe, and expire after at most five minutes.
- API credentials stay server-side. They are never returned to the browser.
- A URL fragment delivers the browser bearer locally without sending it in the
  initial HTTP request; the client then clears the fragment and bearer as
  described above.

These controls are for a single-machine deployment. They are not a reviewed
LAN, Tailscale, or internet exposure design.

## Status, logs, and uninstall

```bash
voicemode service status livekit
voicemode service status livekit-web
voicemode service logs livekit -n 100
voicemode service logs livekit-web -n 100
```

Managed logs live in `~/.voicemode/logs/livekit/`:

- `livekit.out.log` and `livekit.err.log`
- `livekit-web.out.log` and `livekit-web.err.log`

Uninstall the SFU, gateway service files, generated config/start scripts, and
LiveKit environment entries:

```bash
voicemode service uninstall livekit
```

Add `--remove-all-data` to remove the LiveKit log directory too. The CLI asks
for confirmation.

## Troubleshooting

### Missing LiveKit dependency

If a room command reports that the optional dependency is missing, install the
LiveKit extra in the environment that runs VoiceMode:

```bash
uv sync --extra livekit
```

### Browser page does not open or authenticate

Check both services and gateway health:

```bash
voicemode service status livekit
voicemode service status livekit-web
curl --fail http://127.0.0.1:7890/health
```

Always open the page with `voicemode livekit browser open`; visiting the base
URL directly does not supply the bearer. A bearer is consumed by the page's
first connection attempt, so reopen the page before retrying authentication.

### Room not found or room required

Connect the browser first, then run `voicemode livekit rooms list`. Pass the
exact room name if none or multiple rooms match `VOICEMODE_LIVEKIT_ROOM_PREFIX`.

### Room connects but there is no speech

- Turn on the browser microphone and verify browser permission.
- Check the configured TTS and STT endpoints.
- Set `OPENAI_API_KEY` when either selected endpoint is non-local.
- Check both LiveKit log streams.
- Increase `--duration` / `listen_duration_max` if the response is slow.

### Configuration rejected

- Keep the browser host on loopback.
- Keep browser origin equal to `http://<browser-host>:<browser-port>`.
- Use `wss://` or `https://` for any non-loopback SFU URL.
- Do not put credentials, query parameters, or fragments in the SFU URL.

## Real integration test

The opt-in integration test starts an ephemeral loopback-only LiveKit Server,
uses the configured real TTS/STT services, verifies room TTS/STT and
cancellation cleanup, and does not read or write persistent LiveKit state:

```bash
VOICEMODE_RUN_LIVEKIT_INTEGRATION=1 \
  uv run --extra livekit --extra test pytest \
  tests/integration/test_livekit_real.py -v -s --no-cov
```

It requires `livekit-server` on `PATH` and healthy configured TTS/STT services.
This is the repository's real integration gate; it is not evidence that remote
network deployment is supported.

## Current limitations

- The managed SFU and browser gateway are loopback-only.
- LiveKit is selected only with `transport="livekit"` / `--transport livekit`;
  there is no auto route or fallback.
- One scalar message is supported per LiveKit exchange. MCP `turns` and CLI
  `--say`, `--ask`, and `--script` are not supported over LiveKit.
- CLI `--continuous` is not supported over LiveKit. Run one command per
  exchange.
- LiveKit transport does not use local-transport-only controls such as
  `listen_duration_min`, chimes, audio-format selection, speed, or
  `tts_instructions`.
- No TURN deployment, LAN/Tailscale browser exposure, TLS termination, NAT
  traversal hardening, or remote threat-model review has been completed.
- This self-hosted room transport does not restore hosted VoiceMode
  Connect/Auth0.
