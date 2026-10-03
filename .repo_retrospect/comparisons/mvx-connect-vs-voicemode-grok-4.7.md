# mV Connect X vs VoiceMode

Date: 2026-10-02
Reader: Grok 4.7
Trees read:

- `/Users/ibhatt/git/git-personal/mvx-connect` (package `mvx-connect` 0.1.0, CLI `mvx`)
- `/Users/ibhatt/my_local_share/voicemode` (package version `8.12.9+ib`)

This is a judgment after reading both trees. It is not a merge plan copied from a prompt, and it does not change product code.

## How this was read

mV Connect X is small enough to read as implementation. I read the runbook, vision note, handoff, package metadata, CLI, gateway, enhancer chain, Voxtral and remote model-server bridge, Kokoro wrapper, speech gate, durable and streaming spoolers, guardian, turn and intent engines, MCP server and tool contracts, readiness and admission, package/service plans, shared-memory ring and its C ABI, the writer service, the installer, the watchdog, the Electron shell, and the tests that pin those contracts. Runtime `*.wav` dumps and logs under `runtime/` and `bench/runtime-smoke/` were treated as captured evidence of past sessions, not as design. Branding HTML was read only far enough to see that it is identity artwork, not behavior.

VoiceMode is a shipped product of about 69k lines of Python, 110 test modules, docs, a Rust converse hook, LiveKit browser client, and service installers. I read the architecture note, server entry, the converse listen/record/survey/continuation path, the conch lock, LiveKit’s local-room contract, the mlx-audio installer constraints, provider discovery, the unreleased changelog, and the symbol maps of `core.py`, `streaming.py`, `config.py`, `cli.py`, and `tools/service.py`. I inventoried every `voice_mode/**/*.py` module. I did not line-read every test or the archived conversation transcripts under `docs/.archive/`. Claims below about VoiceMode’s conversation loop come from the live path in `converse.py`, `core.py`, `conch.py`, and `livekit/transport.py`, not from the README.

## What each tree actually is

They solve adjacent problems and should stay adjacent.

**VoiceMode is an agent tool that borrows the microphone for one exchange.** The host (Cursor, Claude Code, Codex, and the other clients the plugin installer knows) calls `converse`. The MCP server speaks through an OpenAI-compatible TTS endpoint, then opens the default input device, runs WebRTC VAD, sends a completed utterance to an OpenAI-compatible STT endpoint, and returns text to the same agent that is doing the work. The agent is the conversational brain. Between turns the agent thinks, uses other tools, and calls `converse` again. Optional pieces around that loop are real and heavily tested: conch floor control, a control socket (pause, resume, stop, skip back, skip forward), survey `turns[]`, continuation jobs when an MCP deadline is shorter than a listen, provider failover, conversation logs, and installers for Whisper (port 2022), Kokoro (8880), mlx-audio (8890), and a loopback LiveKit room (SFU 7880, browser gateway 7890).

**mV Connect X is a long-lived local media plane with an MCP control plane beside it.** Audio does not travel through MCP. A browser page, or the virtual-mic writer, streams 16 kHz PCM. A FastAPI process on `127.0.0.1:8766` enhances it, gates it, transcribes it with Voxtral (in-process or via a dedicated model server the code refuses to point at VoiceMode’s ports), and can synthesize Kokoro. The MCP server on stdio or `127.0.0.1:8767` returns session contracts, health, and diagnostics. The host agent is supposed to stay available for other work. `VISION.md` (2026-07-03) says the product is a presentation surface an agent can delegate: script, pacing, barge-in, status back, without pulling the working agent off its task. Guardian Angel is specified as the thing that watches that session and whispers drift.

That split is the whole comparison. VoiceMode’s quality is in the agent contract. mVX’s quality is in the audio session that outlives one tool call.

## Selections

### 1. Keep VoiceMode as the agent-facing conversation product

Selected surface:

- `converse` / `converse_continue` / `pause_conversation`
- Conch: flock for the live call, short re-stamped hold between turns, FIFO queue, callback nudge
- Control channel and history buffer
- OpenAI-compatible provider discovery and failover (Whisper, Kokoro, mlx-audio, OpenAI, Cartesia streaming)
- Service installers, plugin installer, and the Rust pre-tool hook that forces `wait_for_response` and strips agent-supplied listen caps
- Conversation logs and the exchanges reader
- Self-hosted LiveKit as an explicit `transport="livekit"`, not a default

Driver: this is the path a coding agent already depends on, and the failure modes are encoded in tests (conch deadlock, cancelled recording recovery, survey return contract, LiveKit participant cleanup, mlx-audio version ceiling). Replacing it with mVX’s session JSON would throw away a working turn protocol.

Defense: a coding conversation is half-duplex on purpose. The agent must finish hearing before it edits files. Holding the MCP request, or returning a continuation job while the listen continues inside the server, matches that. mVX’s `voice_connect` / `voice_conversation` / `voice_chat` tools return a prompt and a websocket URL. Nothing in the gateway enforces `maxTurns`, expiry, or wake-name resume. Those are labels. Conch is a lock.

### 2. Keep mV Connect X as the long-lived local media plane

Selected surface, because the code actually runs it:

- `gateway/app.py` realtime websocket: enhance, then Silero-or-WebRTC gate, then Voxtral `feed`/`step`, with endpoint hold when the partial does not look finished (`ENDPOINT_HARD_CAP_MS = 4500`)
- Single MLX thread (`_MLX_EXECUTOR`) plus `MLX_REALTIME_LOCK`. Off-thread Metal raises “There is no Stream(gpu, N)” and can kill the interpreter
- `RemoteRealtimeSession` when `MVX_MODEL_SERVER_URL` is set, so the model loads once, off the gateway, and the URL is rejected if the port is 2022, 8880, or 8890
- Enhancer providers behind one `enhance(pcm16) -> (bytes, dict)` shape: adaptive PCM, MossFormer windows, DeepFilterNet3, ECAPA target-speaker isolation with an explicit `opt_in=True` enrollment gate and a persisted embedding (raw audio is not stored)
- Durable spool: raw chunk written before ASR, noise-only transcripts dropped, Parakeet then Qwen3 only on the batch websocket path
- Kokoro HTTP synthesis, browser `speechSynthesis` only as fallback
- Phase-2 virtual mic: `MVXVoice.driver` inside `coreaudiod` does a bounded memcpy from `/mvx_connect_ring`; Python is the producer. Header is 192 bytes, magic `MVXR`, 48 kHz mono float32, 8192-frame ring. Python `ring.py` and `tests/test_mvx_ring_abi.py` freeze that ABI
- macOS installer: editable package, HAL driver, LaunchAgents for gateway, writer, and watchdog
- Browser client and Electron tray as a window onto `http://127.0.0.1:8766/`, not as the protocol

Driver: VoiceMode cannot host a presentation while the same agent is coding. `converse` owns the floor and the request. A delegated demo needs a process that keeps speaking, accepts barge-in, and reports state without a new tool call per audio frame. That process already exists in mVX.

Defense: the virtual-mic design is the right shape for Core Audio. `DESIGN.md` is correct that the IO thread inside `coreaudiod` must not link MLX or PyTorch. The ring ABI is the one mVX contract I would trust in a review: both sides assert the same offsets. VoiceMode has no equivalent and should not grow one inside `converse`.

### 3. Do not merge the repositories

Decision: no shared package, no “port the gateway into `voice_mode/tools`”, no second `converse` that shells out into mVX internals.

Driver: the process models conflict.

| | VoiceMode | mV Connect X |
| --- | --- | --- |
| Who thinks | The host agent | The host agent, plus optional local Qwen for guardian and interruption briefings |
| Who holds the mic | sounddevice, only during listen; or a LiveKit room for one exchange | Browser worklet, or the writer service, for the life of the session |
| Audio API | Record a buffer, POST `/v1/audio/transcriptions` | Streaming PCM on a websocket; deltas during the utterance |
| Metal | mlx-audio is a separate server on 8890, version-capped `<0.4.4` because 0.4.4 crashes Kokoro `istftnet` | In-process MLX unless `MVX_MODEL_SERVER_URL` is set; all GPU work pinned to one thread |
| Duplex | No. Playback finishes, then listen starts. Barge-in is stop/skip on the control socket | User audio can cancel assistant playback; played vs remaining text is computed from a time ratio |
| Multi-agent | Conch | None. A process lock only serializes Metal |

A merge would put two microphone owners and two Metal runtimes in one policy. mVX already had to add a port denylist because that collision is real.

### 4. Do not treat mVX policy reports as runtime truth

Selected to ignore as evidence of a live system:

- `voice_readiness_report()` in `mcp/tools.py` always passes `runtime_preflight={"ready": False, "actionsTaken": []}` and blocked stubs for conversation quality, latency, and failure recovery. The tool cannot return admitted. `readiness.py` is a conservative combiner; the caller starves it.
- `mcp/contracts.py` still says `mcpSdkInstalled: False` and `transportStatus: "contract_only"` while `mcp/server.py` is a real FastMCP server with tools that call the gateway.
- `models/registry.py` marks every model `installed: False`, `status: "not_installed"`.
- `build_mlx_audio_runtime_plan()` is `dryRunOnly: True` and plans a server on port 8000, which is neither the live gateway (8766) nor VoiceMode’s mlx-audio (8890).
- `DuplexConversationLoop` drives `FakeMediaSession`. The report can be “admitted” with no audio device.
- Docs disagree with the code. README and the June 28 handoff still describe Parakeet as the primary live ASR. `app.py` `health()` says Voxtral is primary and Parakeet is the batch fallback. Handoff says 129 tests; `CLAUDE.md` says 234+. MCP examples still point `PYTHONPATH` at `mlx-voice-agent`.

Driver: VoiceMode’s health checks hit real endpoints. Putting mVX’s readiness tool next to them would train agents to distrust status, or worse, to treat a simulated “admitted” duplex report as a microphone test.

Defense: the conservative instinct in `readiness.py` is good. The wiring is not. Until `voice_readiness_report` is fed by the smoke files it already knows how to read (`bench/runtime-smoke/`), it is a fixture, not a gate.

### 5. Borrow only the live audio ideas, and only as a transport boundary

If a later change is made, the only transfer I would accept is a boundary, not a copy:

1. **Semantic hold before end-of-turn.** VoiceMode stops after `SILENCE_THRESHOLD_MS` once speech has been seen and `listen_duration_min` is satisfied. mVX’s `is_semantically_complete` refuses to finalize a short or trailing-conjunction partial until a hard silence cap. That is the right bias: cutting a thinking speaker is worse than waiting. It is deterministic and has no model. It belongs as a listen policy, not as an import of `TurnEngine`.
2. **Played-text versus remaining-text on barge-in.** `PlaybackTracker` splits the assistant string by the fraction of audio already played. VoiceMode’s control-channel stop ends playback and returns a marker; it does not tell the agent what the user did not hear. That context is the useful part of mVX interruption handling. The local-LLM briefing around it is not required for the split itself.
3. **Enhancement before STT, outside the MCP process.** Adaptive PCM is cheap. DeepFilterNet and ECAPA are not, and they pull PyTorch into a process that must stay responsive. They belong in the writer or the model server, not in `record_audio_with_silence_detection`.
4. **One Metal process.** VoiceMode already learned this: mlx-audio 0.4.3 absorbed the serialization lock, and 0.4.4 is pinned out because Kokoro crashes. mVX learned the same thing with `_MLX_EXECUTOR`. Any Voxtral path should be the dedicated server on a non-VoiceMode port (the code’s example is 42007), speaking a streaming API. Do not load Voxtral inside the VoiceMode MCP process.

I would not port guardian narration, spoken-response backchannels (“One sec.”), the fake duplex loop, the voice-clone probe, or the three named session tools.

Driver for the refusals:

- Guardian Angel’s heuristic marks alignment by keyword overlap, and when a local model is present it still takes `aligned` from that heuristic (`angel.py` `summarize`). The disclaimer says the host must not course-correct on the whisper. In a coding agent that instruction fights the host model. In a delegated presentation it might be a status channel. It is not a VoiceMode feature.
- `SpokenResponsePolicy` never speaks. Nothing in the websocket loop calls it. Shipping the policy module would not reduce dead air.
- Clone admission blocks the `fast-local` profile until a probe says `usable`. The catalog is right to refuse to claim a clone works. VoiceMode already selects real Kokoro voices through discovery. A second catalog of `installed: False` rows does not help.

### 6. Keep the port and launchd boundary, and stop the watchdog from owning VoiceMode services

Observed coupling, from code rather than intent:

- mVX model-server URL rejects ports 2022, 8880, 8890.
- `bin/mvx-watchdog` defaults `KOKORO_URL` to `http://127.0.0.1:8880` and `MLX_AUDIO_URL` to `http://127.0.0.1:8890`, and its launchd labels default to `com.voicemode.kokoro` and `com.voicemode.mlx-audio`. A failed probe can `launchctl` restart those services unless a live mVX session is inside the activity window.

Decision: VoiceMode keeps exclusive ownership of `com.voicemode.*` and of ports 2022, 8880, 8890, 7880, and 7890. mVX keeps 8766, 8767, and its model server (42007 unless explicitly changed to something outside that set). The watchdog may probe its own gateway. It must not restart VoiceMode’s LaunchAgents.

Defense: both products can be installed on this Mac at once. A health daemon that restarts the other product’s TTS will look like a random Kokoro outage during a VoiceMode conversation. The denylist in `realtime_voxtral.py` shows the author already saw the collision. The watchdog defaults undo it.

### 7. Leave LiveKit and the virtual mic as different answers to “not the default microphone”

VoiceMode LiveKit, in this fork, is a loopback SFU plus a browser that publishes a mic into a room. `converse(..., transport="livekit")` joins that room for one utterance and returns one final transcript. It is not the removed hosted Connect product. `turns[]` is rejected on that transport.

mVX’s browser client is a raw websocket, not WebRTC. The HAL driver is the other way to leave the default device: every app that selects “mV Connect X” reads cleaned audio from the ring.

Decision: do not implement mVX’s browser path as a LiveKit room, and do not implement LiveKit as a HAL plugin. Use LiveKit when a human and a VoiceMode agent need a room. Use the ring when other applications on the Mac should hear a cleaned mic. Use the mVX websocket when the session itself is the product (continuous transcript, enrollment, guardian, local TTS).

Driver: three transports, three latency and permission stories. Folding them together would hide which one is allowed to touch `coreaudiod`.

## What I am explicitly not selecting

- Rebranding VoiceMode as mV Connect X, I.R.I.S., or TETHERMATRIX. The names describe different jobs. VoiceMode’s name is the MCP tool agents already call.
- Replacing Whisper/Kokoro/mlx-audio with in-gateway Voxtral. Voxtral is a streaming STT, and the batch path still wants a fallback. VoiceMode’s mlx-audio install is a pinned, patched, launchd-managed server. mVX’s in-process loader is a development convenience with a crash history.
- Treating `bench/reports/*.json` as a benchmark. The harness can regenerate them from simulated events. The runtime-smoke JSON under `bench/runtime-smoke/` is the closer thing to a real run, and even that is a snapshot, not a CI gate.
- Copying VoiceMode’s 4.6k-line `converse.py` into the gateway. The file is large because it accumulated cancellation recovery, surveys, and conch. mVX’s `app.py` is already 720 lines and doing too many jobs (HTTP, two websockets, guardian scheduling, enrollment). Growing it into an agent loop would repeat the problem VoiceMode already has.
- Using the Electron tray as the VoiceMode UI. It loads the gateway origin and hides on close. VoiceMode’s UI is the host transcript plus, optionally, the LiveKit page.

## Contradictions I will not smooth over

These are facts about the trees, and they drove the “do not trust the docs” decision.

1. mVX primary ASR. Live health payload: Voxtral. Batch `/ws/.../audio` and `/transcribe`: Parakeet, then Qwen3. README still narrates the older primary-first Parakeet story.
2. mVX MCP runtime. Server is real. Contract manifest says `contract_only`. Readiness always blocked.
3. mVX session modes. Runbook defines three lifecycles. Gateway never reads `maxTurns` or `expiresAfterSeconds`.
4. Enhancement status. `/pipeline/status` lists DeepFilterNet and MossFormer as available models even when the active engine is adaptive PCM. `enhancer.status()` is the truthful field. The static lists are not.
5. Sortformer diarization is named in status and is `liveWired: False`. It is not a feature yet.
6. VoiceMode’s architecture doc still draws only Whisper and Kokoro and “future” plugins. The code has mlx-audio, Cartesia streaming, LiveKit, conch, continuation jobs, and a plugin installer. Trust `converse.py` and the changelog over `docs/concepts/architecture.md`.
7. VoiceMode mlx-audio is capped `<0.4.4` because of a Kokoro broadcast crash. mVX `CLAUDE.md` notes the same crash in an upstream checkout and says short sentences still synthesize. They are depending on the same fragile decoder if both speak through Kokoro.
8. mVX `source_facts` records upstream mlx-audio 0.4.4 with `localRuntimeVerified` false. VoiceMode refuses to run 0.4.4. A shared “latest mlx-audio” pin would be a regression for VoiceMode.

## Recommendations, in the order I would actually do them

These are recommendations to a person deciding what to keep, not changes made in this pass.

1. **Leave both trees where they are.** VoiceMode remains the tool the agent calls. mVX remains the daemon that can outlive that call.
2. **Fix the mVX truth surface before any agent is told to trust it.** `voice_readiness_report` should report gateway `/health` and `/pipeline/status`, or it should not be exposed. Delete or regenerate the claim `transportStatus: contract_only`. Make `list_model_capabilities` read the process environment or say “static scaffold”.
3. **Narrow the watchdog** so it cannot `kickstart` `com.voicemode.*`.
4. **If presentation delegation is the mVX goal, specify the contract `VISION.md` says is missing** before more UI work: what the delegating agent sends (script, pace, voice), what events it gets back (barge-in with played/remaining text, guardian whisper, session end), and which of those the gateway enforces. Do not add that contract by overloading `converse`.
5. **If VoiceMode listen quality is the pain, add a semantic-hold option on the existing VAD loop** and, separately, consider a cleaned-mic *device* (the mVX ring) as an input the user selects. Do not pull DeepFilterNet into the MCP server.
6. **Keep Voxtral on the dedicated model server** if it is used at all. The in-process path is a footgun the code comments already document.
7. **Do not unify Kokoro.** VoiceMode’s 8880 service and mVX’s in-process or 42007 Kokoro can coexist. One of them should be chosen per utterance by the process that is speaking, not by a shared global default that the watchdog restarts.

## Why this is the defensible split

VoiceMode has already paid for the hard parts of an agent product: not dropping the microphone on cancellation, not wedging the conch, not leaking LiveKit participants, not letting an agent stretch a listen past the user’s policy, and not crashing on a bad mlx-audio release. That code is the product.

mV Connect X has already paid for the hard parts of a local duplex audio product: spool-before-transcribe, a single Metal thread, a streaming session that is not an MCP payload, a real-time-safe virtual microphone, and an enrollment path that refuses to store a voiceprint without `opt_in=True`. The policy package around it (admission, fake duplex, readiness that cannot pass, a contract file that denies the SDK) is a scaffold that has drifted away from that audio product. Using the scaffold to redesign VoiceMode would import the drift. Using VoiceMode’s tool loop to redesign the gateway would import a half-duplex agent into a process that exists so the agent can look away.

The selection is therefore: **agent contract stays in VoiceMode; live audio session stays in mVX; shared machine resources stay partitioned by port and launchd label; simulated reports stay out of both decision paths.**
