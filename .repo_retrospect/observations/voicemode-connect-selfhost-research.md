# VoiceMode Connect self-hosting research

Research date: 2026-09-07  
Repository: `/Users/ibhatt/Downloads/voicemode`  
Branch/HEAD: `patch-fix-for-voicemode-8.12.0` / `5c1b3e4d9421cd365d039da1d29827a0a83a18c7`

The clone is complete enough for repository-history conclusions: `git rev-list --count HEAD` reports 2,147 commits and `git rev-parse --is-shallow-repository` reports `false`. The working tree already contained unrelated user changes; none were touched.

## Current Architecture

### What is actually in the current tree

Current VoiceMode Connect is no longer implemented end-to-end in this repository. The current tree contains documentation/configuration for two cloud-facing entry points and the remaining local authentication helper:

1. **Cloud MCP path (outbound agent conversations).** `.claude/skills/voicemode-connect/SKILL.md:8-14,20-50` tells an agent to connect `mcp-remote` to `https://voicemode.dev/mcp`. The hosted MCP server exposes `status` and `converse`; a phone/browser connects separately over WebSocket, and STT/TTS runs on that client (`.claude/skills/voicemode-connect/SKILL.md:43-60`). No implementation or parameter schema for those hosted MCP tools is present here. The same skill still links to deleted `docs/connect/` pages (`.claude/skills/voicemode-connect/SKILL.md:64-77`), so those links are stale in this checkout.
2. **Inbound Claude Code channel path.** The formerly bundled TypeScript channel was extracted to the separate `IB-QA/voicemode-channel` repository. The extraction is recorded in commit `33c62966629adfec2fbb10f27370ff02c2a33a02` (2026-03-23 18:39:07 +1100) and `CHANGELOG.md:392-400`. Thus, there is no current WebSocket relay client in this tree.
3. **Auth helper retained for the external channel plugin.** `voice_mode/auth.py:1-30` hardcodes the Auth0 tenant, public native-app client ID, scopes, and audience. It implements authorization-code + PKCE with a localhost callback (`voice_mode/auth.py:103-119,207-299,523-549,552-653`), token exchange/refresh/userinfo against Auth0 (`voice_mode/auth.py:306-420`), and credential lifecycle (`voice_mode/auth.py:432-520`).
4. **CLI auth surface.** `voice_mode/cli.py:2382-2557` retains only `voicemode connect auth login|logout|status`; its docstring explicitly says the credentials are used by `voicemode-channel` (`voice_mode/cli.py:2421-2428`). The legacy connect client/status/up/down commands are gone.
5. **Credential persistence.** `voice_mode/credential_store.py:20-27,50-109,190-224` stores the Auth0 token either in `~/.voicemode/credentials` (mode 0600, default) or an optional keyring backend.

Other current references:

- `.claude/skills/voicemode/SKILL.md:488-512` points users to `app.voicemode.dev`, says the client device handles audio, and notes that the hosted web app can be configured with custom TTS/STT endpoints. That changes speech-provider endpoints, not the Connect relay.
- `CHANGELOG.md:394-400` is the authoritative explanation for removal of the bundled Python Connect client and extraction of the channel server.
- `getvoicemode.com` occurrences are website/installer/package metadata (`pyproject.toml:84`, `install.sh:3-8,1158`, `CHANGELOG.md:287,2403`), not Connect transport endpoints.

### Current conch is local coordination, not the relay

The current “conch” is a local, filesystem-backed single-speaker lock:

- `voice_mode/conch.py:101-130` defines the holder payload and its two liveness layers: an OS file lock during an active call and an on-disk, expiring hold between turns.
- `voice_mode/conch.py:310-379,479-549` implements atomic acquisition, hold/release, stale-holder handling, and queue promotion.
- `voice_mode/conch_queue.py:1-42,80-128` defines the FIFO waiter registry and grant file; `voice_mode/conch_queue.py:350-539` handles registration and next-grantee selection.
- `voice_mode/tools/conch.py:1-31,80-180` exposes status/wait/callback/heartbeat/leave/give/bump/release to remote MCP callers; remote waiter liveness is a heartbeat TTL, but the state still lives beside `~/.voicemode/conch` on the VoiceMode host.
- `voice_mode/cli_commands/conch.py`, `voice_mode/conch_ops.py`, and `voice_mode/conch_notify.py` are respectively the CLI front end, shared operations, and callback notification support.
- `voice_mode/tools/converse.py:3132-3137,3210-3254,3541-3569` integrates this lock into local `converse`.

No evidence in this tree ties the conch to the hosted relay protocol. It arbitrates multiple agents that share one local VoiceMode audio host. Any server-side “one active mobile conversation” rule in voicemode.dev would be separate code and is not available here.

### Historical Connect implementation still recoverable from Git

The last tree before the legacy Python client and bundled channel were removed is commit `75a9bdeda8126760f89f5a4ec862b5758f0490f9` (2026-03-23 02:31:11 +1100). Relevant files recoverable from that tree are:

- `channel/gateway.ts` — Auth0 credential loading/refresh, configurable gateway URL, Bearer-authenticated WebSocket, reconnect/backoff, `ready`, agent capability registration, and 25-second `ping`.
- `channel/index.ts` — MCP channel capability, inbound `user_message_delivery` to `notifications/claude/channel`, and the `reply` tool that emits `speak`.
- `channel/README.md` — setup and environment-variable contract.
- `voice_mode/connect/client.py` — superseded Python WebSocket client, device status, capability/presence registration, message delivery, reconnect, and keepalive.
- `voice_mode/connect/config.py` — `VOICEMODE_CONNECT_*` mapping and deterministic device identity.
- `voice_mode/connect/messaging.py` — JSONL inbox plus Claude team-inbox symlink delivery.
- `voice_mode/connect/users.py`, `presence.py`, `types.py`, `watcher.py` — local mailbox records, presence types, and configuration watching.
- `voice_mode/tools/connect_status.py` — MCP presence/status front end.
- `voice_mode/connect_registry.py` — older monolithic client superseded by `voice_mode/connect/`.
- `voice_mode/data/hooks/{check-notifications,connect-session-start,connect-session-end,on-team-created,stop-notifications}.{sh,json}` — lifecycle/inbox delivery hooks.
- `voice_mode/templates/launchd/com.voicemode.connect.plist` and `voice_mode/templates/scripts/start-voicemode-connect.sh` — old service wrapper.
- `docs/connect/` — old architecture and command documentation.

Commit `0ef60e8b0f36970a709bcdbad8300a1640dc8760` (2026-03-23 22:11:55 +1100) deleted those Python files because the external `voicemode-channel` plugin had superseded filesystem inbox delivery. Commit `33c62966...` separately removed the bundled `channel/` copy after extraction.

### Endpoints and expected contracts

#### Endpoints evidenced for the current arrangement

- `https://voicemode.dev/mcp` — hosted streamable MCP endpoint, configured literally in `.claude/skills/voicemode-connect/SKILL.md:20-30`. The repository does not establish exact HTTP methods, OAuth discovery/registration endpoints, tool schemas, consent screens, or server implementation.
- `wss://voicemode.dev/ws` — default channel gateway URL in the last bundled channel, overridable through `VOICEMODE_CONNECT_WS_URL` (`channel/gateway.ts@75a9bded:23-35`).
- `https://dev-2q681p5hobd1dtmm.us.auth0.com/authorize`, `/oauth/token`, and `/userinfo` — hardcoded issuer endpoints generated by `voice_mode/auth.py:327-340,371-383,413-419,523-549`.
- `http://localhost:8765..8769/callback` — local PKCE callback selected by `voice_mode/auth.py:32-35,103-119,207-299`.

There is no `device_code` implementation, pairing-code flow, or repository-owned OAuth consent implementation. Current-tree searches for `device_code`, relevant `pairing`, and Connect consent code found none. Browser consent is delegated to Auth0; OAuth for the hosted `/mcp` endpoint is implemented outside this repository.

#### WebSocket contract evidenced by the final bundled channel/client

The extracted channel’s expected minimum is:

- Open `VOICEMODE_CONNECT_WS_URL` with `Authorization: Bearer <Auth0 access token>` (`channel/gateway.ts@75a9bded:255-270`).
- Receive `{"type":"connected","sessionId":...}`, then send:
  - `{"type":"ready","device":{"platform":"channel-server","appVersion":"0.1.0","name":"channel@<host>"}}`
  - `{"type":"capabilities_update","platform":"claude-code","users":[{"name":...,"host":...,"display_name":...,"presence":"available"}]}`
  (`channel/gateway.ts@75a9bded:293-305,347-389`).
- Send literal text `ping` every 25 seconds and accept literal `pong` (`channel/gateway.ts@75a9bded:392-399`).
- Send agent speech as `{"type":"speak","id":...,"text":...,"timestamp":...,"voice"?:...,"waitForResponse"?:true}` (`channel/index.ts@75a9bded:112-168`).
- Receive inbound speech transcripts as `{"type":"user_message_delivery","text":...,"from"?:...,"userId"?:...}`; the channel turns these into `notifications/claude/channel` (`channel/index.ts@75a9bded:175-194,243-278`).
- The superseded Python client additionally expected `devices`, `heartbeat`/`heartbeat_ack`, `ack`, `error`, and `user_message_delivery`, and sent `delivery_confirmation` (`voice_mode/connect/client.py@75a9bded:399-476`).

An early Cloudflare Worker implementation is present only on historical refs, not in HEAD: `voicemode-dev/src/index.ts@15ba527e:55-70,126-259` routed `/health` and `/ws` to a per-user Durable Object and validated Auth0 JWTs; the Durable Object exposed internal `/health` and `/info` plus WebSocket upgrade (`voicemode-dev/src/durable-objects/websocket-gateway.ts@15ba527e:298-340`). Its protocol defined `auth`, `ready`, `transcription`, `heartbeat`, `resume` client messages and `speak`, `listen`, `stop`, `ack`, `connected`, `heartbeat[_ack]`, `error`, and `session_resumed` server messages (`voicemode-dev/src/websocket/protocol.ts@15ba527e:26-267`). This is useful design evidence but is an early January 2026 snapshot; it is not proof of the current production protocol. Later changelog evidence says the Python client was aligned to a separate VMD-124 gateway specification (`CHANGELOG.md:513-517`).

Because the current web app, iOS app, `voicemode-channel`, and production `voicemode-dev` backend are separate repositories/services, this clone cannot provide every route or payload those current clients use. Those source repositories (or captured network/API documentation) are required for an exact compatibility implementation.

## LiveKit History (with commit SHAs and dates)

### Finding

LiveKit was real and self-hostable. The claim that it was later replaced by a proprietary/commercial Connect relay is not supported by this history:

- Initial bundled LiveKit frontend/admin material landed in `535f7daf2d19bc53241219f49ea8b77bbcc46d73` on 2025-06-12 23:31:19 +1000.
- Complete managed-service integration is recorded by `d520397af49a0ee841f87f3259572f75b16d3958` on 2025-08-13 and the 2.22.0 changelog (`CHANGELOG.md` in the pre-removal tree, lines 1452-1482).
- LiveKit Python support was removed in `e26a915ccadd84522ef0f3d073838cef7e90478a` on 2026-01-07 03:03:57 +1100.
- The frontend/templates/vendor copies were removed in `9a3cd53c8dfbdf621e027f26755623da881df9be` on 2026-01-07 03:35:46 +1100.
- Documentation cleanup followed in `fc323e5aa5332845a06056c4cbf1d806a5c2d4d2` on 2026-01-07 04:09:10 +1100.
- VoiceMode Connect’s skill first landed in `d5ecfdc3dd4d230c434fb37957a6547cd09eb826` on 2026-02-01, and Connect was released in 8.1.0 (`CHANGELOG.md:562-574`). The gateway/client work began in late January. Thus Connect followed LiveKit chronologically, but the commits do not say it replaced LiveKit.

### Stated removal reason

There is no rationale in the removal commit beyond removing the feature. `e26a915c...` enumerates deleted code and says local microphone remains; `fc323e5a...` adds a changelog entry saying users must use local microphone. Neither commit mentions cost, proprietary licensing, a commercial relay, Connect, maintenance burden, security, or technical failure. Any stronger “why” requires an upstream issue/PR discussion for VM-353 or maintainer testimony.

The exact immediate parent tree of the Python removal is `e32220e1220a5dc1cb6061515a18abfa686eec79`; it is the last Git tree in that ancestry containing the complete Python LiveKit path. (Its commit timestamp is later than the child’s author timestamp because of the branch/merge topology.) The last LiveKit-specific functional change before deletion was `a8791efa92f1b69d43732f1d0b17e5c6643c07e2` (2025-11-24), which made LiveKit optional for Python 3.14 compatibility.

### What the old integration did

- **Room selection:** `livekit_converse()` listed rooms through `LiveKitAPI` and selected the first room with participants; it did not create the room itself (`voice_mode/tools/converse.py@e32220e1:966-1024`).
- **Agent participant:** each `converse` call built a short-lived `VoiceAgent`/`AgentSession`, attached configured OpenAI-compatible STT/TTS and Silero VAD, joined as `voice-mode-bot`, spoke the supplied message, waited for a transcription, then disconnected (`voice_mode/tools/converse.py@e32220e1:1026-1143`). This was per-call integration, not a separate always-running agent worker.
- **Agent token minting:** Python minted a room-scoped JWT with publish/subscribe grants (`voice_mode/tools/converse.py@e32220e1:1101-1111`).
- **Browser token and room:** Next.js `GET /api/connection-details` checked a shared password, generated random participant and room names, minted a 15-minute JWT with room join/publish/data/subscribe grants, and returned `{serverUrl, roomName, participantName, participantToken}` (`voice_mode/frontend/app/api/connection-details/route.ts@e32220e1:1-90`).
- **Browser client:** the React page fetched connection details, connected with `livekit-client`, enabled the microphone, and rendered the LiveKit voice-assistant controls/audio (`voice_mode/frontend/app/page.tsx@e32220e1:6-18,20-58,68-80,144-172`).
- **Server deployment:** `voice_mode/tools/livekit/install.py@e32220e1:27-120,124-308` downloaded/installed `livekit-server`, generated a dev-key YAML with RTC ports, and installed launchd/systemd services. Templates and helper/status code were also bundled.

Principal deleted source:

- `voice_mode/tools/livekit/{install.py,uninstall.py,frontend.py,production_server.py,__init__.py}`
- `voice_mode/utils/services/livekit_helpers.py`
- `voice_mode/frontend/` (Next.js source plus accidentally tracked build output)
- `vendor/livekit-admin-mcp/`
- `vendor/livekit-voice-assistant/voice-assistant-frontend/`
- `voice_mode/templates/{launchd,systemd}/com.voicemode.{livekit,frontend}.*`
- `build_hooks.py`, `tests/test_livekit_mcp_tools.py`, `tests/test_livekit_service.py`, and `docs/guides/livekit-setup.md`

The surviving archive documents corroborate configuration and service behavior: `docs/.archive/LIVEKIT_SETUP.md:1-108,210-239`, `docs/.archive/livekit-implementation-summary.md:1-99`, and `docs/.archive/livekit-service-design.md:1-59`.

One important defect in the last frontend source is a hardcoded `wss://x1:8443` despite the environment-variable comment (`voice_mode/frontend/app/api/connection-details/route.ts@e32220e1:4-11`). A resurrection must fix that and must not keep the documented default password/dev key for exposed deployments.

## Self-Hosting Options

### Option 1 — Minimal current-protocol relay plus a new personal web client (recommended)

Build a deliberately small single-user service:

1. WebSocket `/ws`, routing one browser/device connection and one channel connection.
2. Shared-secret authentication at upgrade time (for example, Bearer token), replacing Auth0.
3. The message subset actually used by the extracted channel: `connected`, `ready`, `capabilities_update`, `ping`/`pong`, `speak`, and `user_message_delivery`; optionally `ack`, `devices`, `error`, and delivery receipts.
4. A local web client that performs microphone/STT and TTS/speaker work and speaks the protocol above.
5. The external `voicemode-channel` plugin pointed at the service with `VOICEMODE_CONNECT_WS_URL`.

This avoids reproducing multi-tenant accounts, Durable Objects, OAuth consent, device pairing, resumable sessions, and the opaque hosted MCP `/mcp` implementation. For one user on a LAN/Tailscale network, Auth0 can safely be replaced with one high-entropy secret if TLS and origin/access controls are handled correctly. `voice_mode/auth.py` would then be unnecessary for this personal path; the external channel plugin would need a token override or small auth patch because its historical bundled version hardcoded Auth0 token refresh.

Rough effort: **3–5 focused engineering days for a LAN/Tailscale prototype; 1–2 weeks for robust reconnect, browser UX, TLS/reverse proxy, tests, and service packaging.**

### Option 2 — Reimplement the hosted Connect relay/API for existing clients

Required surface, to the extent this repository proves it:

- Hosted streamable MCP at `/mcp`, OAuth-enabled, with `status` and `converse`.
- WebSocket `/ws` with account/device/agent routing, the wire messages above, presence/capabilities, correlation IDs, keepalive, and probably queuing/resumption.
- OAuth issuer/discovery/consent accepted by `mcp-remote`, plus Auth0-compatible JWT verification or coordinated patches to every client.
- Web/mobile client login, endpoint override, target-device selection, and STT/TTS settings.
- Conversation ownership/concurrency rules; the current local conch cannot simply be reused as a distributed token without designing server-side ownership and expiry.

Agent-side gateway URL configurability existed: both the removed Python client (`voice_mode/connect/config.py@75a9bded:33-35`; old config at `voice_mode/config.py@75a9bded:633-647`) and bundled channel (`channel/gateway.ts@75a9bded:27`) honored `VOICEMODE_CONNECT_WS_URL`. The current hosted MCP URL appears only as a literal setup argument and can be manually changed to another URL. In contrast, this repository contains no evidence that the current iOS/web clients can change their relay base URL. Their source or traffic capture is the blocker.

Auth0 can be stubbed for a controlled, patched single-user ecosystem, but not transparently for unmodified clients that validate a particular issuer/audience or rely on hosted OAuth discovery. A shared secret is practical only when the channel and web/mobile client are both under the operator’s control.

Rough effort: **3–6 weeks for a compatible single-user replacement with a new web client; longer/indeterminate for drop-in compatibility with the existing iOS app because its source and endpoint/auth behavior are absent.**

### Option 3 — Resurrect the old LiveKit path

This is technically feasible because the complete pre-removal tree and service installer are in Git, and self-hosted `livekit-server` is the intended server. It may be the fastest way to restore the old browser-to-agent audio experiment:

- recover the relevant files from `e32220e1...`;
- update old LiveKit Python/React APIs and dependency versions;
- replace `wss://x1:8443`, dev keys, and default password with configuration/secrets;
- configure TLS, UDP/TCP RTC ports, and TURN for access beyond a simple LAN;
- test the per-call `AgentSession` lifecycle against current STT/TTS providers and current VoiceMode `converse`.

However, it does **not** recreate current VoiceMode Connect. It transports live media through a LiveKit room and runs STT/TTS in the agent session, whereas current Connect documentation says STT/TTS runs on the phone/browser and text commands/transcriptions traverse the relay. Existing VoiceMode Connect mobile/web clients are not shown to support LiveKit. Porting the old integration into VoiceMode 8.12 also means reconciling roughly six months of changes in a large `converse.py`.

Rough effort: **4–7 days for an insecure/local proof of concept; 2–3 weeks for dependency updates, integration cleanup, TLS/TURN, security, and reliable service management.**

## Recommendation with rough effort estimate

For a personal, wholly self-hosted stack, implement the **minimal current-protocol WebSocket relay plus a small self-hosted browser client**, and use the extracted `voicemode-channel` as the agent adapter. Put it behind Tailscale or a TLS reverse proxy and use a single strong shared secret. Estimated effort is **1–2 weeks for a dependable personal deployment**.

Do not start by resurrecting LiveKit unless the actual goal is specifically a WebRTC room-based browser experience and compatibility with the current VoiceMode Connect apps is unimportant. LiveKit is recoverable and may yield a demo quickly, but it is an older, different architecture with more media/network deployment complexity and no demonstrated path to the current clients.

Do not attempt a drop-in clone of `voicemode.dev/mcp` first. The hosted MCP implementation, current production gateway, current web client, iOS client, OAuth discovery/consent, and any pairing implementation are absent from this clone. Exact compatibility research requires the `IB-QA/voicemode-dev`, `IB-QA/voicemode-channel`, web-client, and iOS repositories (if accessible), or an authorized protocol capture from the current service.
