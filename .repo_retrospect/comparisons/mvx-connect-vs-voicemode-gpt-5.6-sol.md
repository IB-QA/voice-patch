# mvx-connect vs VoiceMode: repository retrospective and direction

**Review date:** 2026-10-02  
**Repositories reviewed:**

- `/Users/ibhatt/git/git-personal/mvx-connect`
- `/Users/ibhatt/my_local_share/voicemode`

## Executive conclusion

These repositories should not be merged wholesale, and mvx-connect should not replace VoiceMode.

My recommendation is:

1. **Keep VoiceMode as the product and control-plane foundation.**
2. **Treat mvx-connect as an Apple-real-time research and incubation repository.**
3. **Port only a small set of mvx-connect ideas through explicit VoiceMode interfaces, after they pass real-hardware and restart/soak gates.**
4. **Do not import mvx-connect's gateway, simulated readiness/admission layer, Guardian policy, Electron shell, or current shared-memory driver implementation into VoiceMode's core.**
5. **Before adding a new real-time engine, reduce VoiceMode's internal coupling and repair its test, installer, hook, and documentation drift.**

The key distinction is maturity of responsibility, not raw novelty:

- VoiceMode already owns the hard product responsibilities: MCP contracts, local and cloud provider failover, cancellation, continuation, multi-agent coordination, control-channel semantics, persistent logs, secure HTTP serving, service lifecycle, packaging, and multiple operating systems.
- mvx-connect has the stronger experimental work in direct low-latency browser audio, semantic endpointing, interruption, spool-first durability, Apple-native virtual-microphone plumbing, and explicit latency/readiness targets.
- mvx-connect's strongest ideas are valuable precisely because they can be isolated as an engine or transport. Its weakest parts are the parts that pretend to be a mature product/control plane.

The defensible target is therefore **one stable VoiceMode product with optional engine and transport adapters**, not one enlarged repository containing two orchestration systems.

## Scope, method, and evidence

I formed this judgment from the repositories themselves rather than from a preselected keep/drop list.

The review covered, for mvx-connect:

- Python package source and entry points
- FastAPI/browser gateway and browser client
- speech gate, VAD, speaker isolation, enhancement, TTS, STT, interruption, and Guardian paths
- registry, admission, readiness, health, lifecycle, and watchdog logic
- MCP server and MCP-UI surface
- Electron wrapper
- CoreAudio C driver
- Python/C shared-memory ABI and ring-buffer logic
- launchd/install/uninstall scripts
- benches and runbooks
- package/build metadata
- tests and fixtures

The review covered, for VoiceMode:

- FastMCP server, CLI, configuration, core audio, and package metadata
- `converse` scalar, multi-turn, survey, cancellation, and continuation paths
- local and cloud TTS/STT selection, failover, retries, compression, and error handling
- playback streaming, buffering, replay history, pause/resume/stop/skip controls
- conch ownership, FIFO waiters, grants, callbacks, and stale-state recovery
- conversation and event persistence
- local and HTTP transports, MCP bridge, and secure serving middleware
- self-hosted LiveKit browser-room path
- Whisper, Kokoro, MLX Audio, and LiveKit installation/lifecycle code
- standalone installer package
- plugin/hook integration, including the Rust hook
- docs, archived design material, changelog, scripts, templates, workflows, tests, and runbooks

Graph indexing gave a useful scale check:

- **mvx-connect:** 1,556 graph nodes, 5,822 edges, 105 Python files, 45 indexed test files
- **VoiceMode:** 8,620 graph nodes, 29,893 edges, 249 Python files, 113 indexed test files

Those counts are not quality scores. They establish that VoiceMode carries a much larger product and compatibility surface.

Fresh test evidence from the reviewed checkouts:

- **mvx-connect:** `248 passed, 2 skipped` in 0.88 seconds.
- **VoiceMode:** test collection stops with a `SyntaxError` in `tests/test_provider_selection.py`; the function name `test_global_set_to_mlx_repo_id_IB-QAs_env` contains a hyphen. No VoiceMode test result beyond collection is therefore valid for this snapshot.

The VoiceMode checkout was already heavily modified before this review. I did not alter or clean those changes. Findings involving modified files are snapshot findings and should be separated from claims about the last committed revision.

## What the repositories actually are

### mvx-connect

mvx-connect is an ambitious, Apple-Silicon-oriented real-time voice prototype. Its center of gravity is a direct interactive audio system:

- browser capture and playback
- a FastAPI/WebSocket gateway
- Voxtral-style streaming STT
- Kokoro TTS
- enhancement and VAD
- speaker enrollment/isolation
- semantic endpointing and barge-in
- a Guardian/intent layer
- model registry, admission, and readiness concepts
- a native CoreAudio virtual microphone fed through shared memory
- launchd supervision and a small Electron wrapper
- MCP and MCP-UI integration around the system

The repository aims at a tight local appliance: models, browser, native audio device, and orchestration running together on one Apple machine.

That is also its constraint. It is not merely optimized for Apple Silicon; many assumptions are embedded in process launch, paths, driver integration, model selection, and operations. The system is most convincing as a lab for a particular hardware topology.

### VoiceMode

VoiceMode is a mature, broad MCP voice product. Its center of gravity is a durable agent-facing contract:

- a small default MCP tool surface
- direct local microphone/speaker conversations
- multiple local and cloud OpenAI-compatible providers
- endpoint-ordered failover
- service installers and supervision on macOS and Linux
- native Windows accommodations
- explicit cancellation and long-request continuation
- multi-agent single-speaker coordination
- external playback controls
- persistent event, conversation, job, and audio records
- optional HTTP and LiveKit access
- plugin/client integration

Its architecture has accumulated debt, but that debt largely comes from carrying real compatibility and recovery obligations over many releases. VoiceMode is a product with too much concentrated orchestration. mvx-connect is a prototype with too much product framing around experimental internals.

## Comparative judgment

| Dimension | Stronger repository | Reason |
| --- | --- | --- |
| Stable agent-facing contract | VoiceMode | MCP semantics, selective tool exposure, cancellation, continuation, and result contracts are substantially developed. |
| Provider and deployment flexibility | VoiceMode | Local/cloud endpoints, failover, retries, macOS/Linux/Windows accommodations, and multiple installers already exist. |
| Multi-agent coordination | VoiceMode | Conch ownership, FIFO queueing, grants, callbacks, stale recovery, and CLI/MCP control are real subsystems with focused tests. |
| Operational history | VoiceMode | Changelog and code show repeated fixes for cancellation, service supervision, security, packaging, and migration failures. |
| Direct browser real-time loop | mvx-connect | Browser/gateway interaction is more central, direct, and latency-driven than VoiceMode's room transport. |
| Explicit real-time performance intent | mvx-connect | Latency budgets, readiness concepts, interruption, and endpointing are first-order architecture concerns. |
| Native Apple audio experimentation | mvx-connect | CoreAudio virtual-device and shared-memory work has no equivalent in VoiceMode. |
| Durability-first media thinking | mvx-connect | Spool-first concepts and explicit preservation of captured media are strong design inputs. |
| Current test command | mvx-connect | Its suite is green in the reviewed checkout; VoiceMode currently fails collection. |
| Breadth and production survivability | VoiceMode | It handles many more failure boundaries and host environments. |
| Architectural simplicity | Neither | mvx-connect concentrates too much in its gateway; VoiceMode concentrates too much in several very large modules and duplicates policy paths. |
| Documentation accuracy | Neither | mvx-connect overstates maturity; VoiceMode contains extensive but materially stale and contradictory documentation. |

## Architectural analysis

### 1. Control plane

VoiceMode's control plane is the stronger base.

Its MCP boundary is not a thin demo wrapper. It includes:

- selective tool loading to control context cost
- a well-developed `converse` contract
- ordinary-return control markers rather than using cancellation for every interruption
- long-turn continuation jobs that preserve in-flight work across MCP request deadlines
- service-management tools and CLI parity
- HTTP serving and a stdio-to-HTTP bridge
- resource and prompt surfaces
- explicit cleanup of shared HTTP clients

mvx-connect has MCP and UI integration, but its central contract is the gateway's internal topology. Registry, admission, and readiness objects are presented as if they are authoritative, while parts of the evidence are synthetic, inferred, or placeholder-driven. That is acceptable in an experiment; it is unsafe as a product control plane because callers cannot distinguish measured readiness from declared readiness.

**Decision:** retain VoiceMode's public control plane. Do not add a second top-level gateway/control contract from mvx-connect.

### 2. Conversation orchestration

VoiceMode handles more states than mvx-connect:

- speak-only and speak/listen turns
- surveys with indexed partial results
- TTS and STT failure distinction
- playback controls
- spoken repeat/wait/break behavior
- cancellation cleanup
- conch ownership
- continuation deadlines
- persistent logs and jobs

The problem is concentration. `voice_mode/tools/converse.py` combines schema, validation, recording, VAD, TTS sequencing, survey execution, controls, conch handling, logging, cancellation, and presentation. Similar overload exists in `cli.py`, `config.py`, `streaming.py`, and `tools/service.py`.

mvx-connect separates some real-time ideas more clearly—speech gating, enhancement, Guardian decisions, model service state—but then recombines too much in the gateway and browser client.

**Decision:** use VoiceMode semantics but split their implementation. mvx-connect should not supply the replacement orchestrator.

### 3. Provider model and failover

VoiceMode is decisively ahead. It supports ordered STT/TTS endpoints, local-vs-remote behavior, retries for transient local STT errors, model resolution per provider, voice mapping, shared clients, and user-readable error parsing.

There is still internal overlap:

- `providers.py` contains provider/model selection.
- `provider_discovery.py` contains endpoint probing and metadata.
- `simple_failover.py` contains the operational path used for failover.
- LiveKit uses a narrower selection path and does not yet inherit all local-path behavior.

The changelog itself records a past attempt to consolidate provider systems, while the current tree still exposes multiple concepts. This is survivable but increases the chance that one transport fixes model selection or retries while another does not.

mvx-connect's model server setup is more tightly coupled to particular model processes. Its registry is conceptually richer but operationally less trustworthy because advertised/admitted/ready states are not consistently backed by live evidence.

**Decision:** keep VoiceMode endpoint and provider ownership. Extract one canonical provider-resolution service and make every transport use it.

### 4. Real-time media path

This is mvx-connect's most important contribution.

Its architecture treats the following as one timed loop:

- audio arrives continuously
- enhancement and speech gating happen before expensive inference
- speaker evidence can influence admission
- partial transcription and semantic endpointing influence when a turn closes
- user speech can interrupt output
- system readiness and model latency affect admission

VoiceMode's local path is responsive and increasingly sophisticated, but it remains a turn-oriented pipeline: synthesize/play, capture, VAD-end, transcribe, return. Its control channel provides deterministic barge-in and replay, and `turns` pipelines synthesis, but it is not a general duplex real-time engine.

**Selection:** port the *contractual ideas*, not the gateway:

- timestamp every media boundary
- distinguish transport, queue, model, and playback latency
- allow incremental endpointing signals
- make interruption a first-class engine event
- preserve audio before downstream inference where configured
- expose truthful readiness derived from live components

### 5. Audio durability

mvx-connect's spool-first instinct is good: captured audio should become durable before optional enhancement, transcription, or policy stages can lose it.

VoiceMode already saves audio and conversation records, creates `latest-*` links, persists survey replies immediately, and recovers cancellation work. But persistence behavior is distributed across configuration, conversation logging, cancellation recovery, and STT functions. Some paths depend on user save preferences, which is correct for privacy but means durability guarantees are conditional and harder to reason about.

**Selection:** adopt a clearly named media-journal abstraction in VoiceMode:

- disabled by default unless current save settings request it
- append/commit semantics explicit
- one record linking raw capture, transformed upload, transcript, provider attempt, and final conversation event
- bounded retention and privacy documented

This preserves VoiceMode's user-controlled privacy while gaining mvx-connect's failure-analysis discipline.

### 6. Browser and remote transport

VoiceMode's restored self-hosted LiveKit path is operationally safer than exposing mvx-connect's gateway directly:

- loopback-only defaults
- generated credentials
- a managed SFU and browser service
- explicit room matching
- clear separation from the removed hosted product
- cleanup of temporary participants

However, it is less integrated than the local path. The current LiveKit code uses a constrained scalar-message contract, takes only the first configured speech endpoints in places, and does not inherit all provider/failover/model-resolution behavior.

mvx-connect's browser loop is more immediate and more representative of a real-time product experience, but it is also more monolithic and carries model/process assumptions into the gateway.

**Decision:** keep LiveKit as VoiceMode's supported browser/room transport. Use mvx-connect's browser flow as a UX and latency reference. If a direct WebRTC/WebSocket transport is later justified, implement it as another VoiceMode transport adapter, not as a new application root.

### 7. Native virtual microphone

mvx-connect's CoreAudio driver is strategically interesting. A virtual microphone can let any local application consume agent-generated audio without embedding VoiceMode.

The current implementation is not ready to ship:

- shared-memory producer/consumer semantics are not complete enough for reliable overrun accounting
- the consumer does not visibly advance the shared `read_index`, so occupancy/overrun diagnostics are not authoritative
- the device does not clearly remap shared memory after a producer restart
- reported CoreAudio latency is effectively zero despite a non-zero buffering and scheduling path
- the installation and path assumptions are tightly local and Apple-specific
- real sleep/wake, device-restart, producer-crash, and long-run tests are missing

These are not cosmetic issues. AudioServerPlugIn code runs in a sensitive host process. A stale mapping or dishonest latency report is a reliability problem for every application using the device.

**Decision:** keep this out of VoiceMode core. Graduate it only as a separately installed, separately versioned macOS adapter after ABI and lifecycle hardening.

### 8. Multi-agent coordination

VoiceMode's conch subsystem is a real differentiator:

- process-safe ownership
- stale lock detection
- hold/release semantics
- FIFO waiters
- explicit grants
- callback waiters
- promotion without callback starvation
- unclaimed-grant TTL recovery
- CLI and MCP visibility

mvx-connect's Guardian is trying to solve a different problem: infer conversational intent and decide whether the agent should act or speak. That can be useful, but it should not replace deterministic floor ownership. Inferred intent cannot safely arbitrate multiple agents contending for one physical audio channel.

**Decision:** keep deterministic conch ownership. Guardian-like inference may be tested as optional endpointing/advisory metadata, never as the authoritative lock or permission system.

### 9. Service lifecycle and installation

VoiceMode is broader and more battle-tested:

- launchd and systemd templates
- install/uninstall/status/start/stop/restart/enable/disable/logs
- multiple voice backends
- process and port checks
- package metadata and release workflows
- platform dependency detection

But the standalone installer has drifted from the main CLI:

- it claims local service installation as a supported end-to-end flow
- it builds `voicemode service install whisper --model <name>`, while the current unified service command's placement/option contract does not match this invocation
- its shell-completion step only checks for `.bashrc` and reports success without installing completion code
- it emits old command suggestions such as `voicemode whisper install` and `voicemode kokoro install`
- its README references a missing `DECISIONS.md`
- its platform detection contains a `/proc/version` read pattern that can consume the stream before the second check

mvx-connect's launchd/watchdog path is narrower and easier to understand, but it contains hard-coded topology and does not carry VoiceMode's cross-platform burden.

**Decision:** keep VoiceMode lifecycle ownership, but eliminate the separate installer logic or make it call a versioned machine-readable install API from the main package.

### 10. Security

VoiceMode has stronger explicit security work:

- direct-peer/trusted-proxy handling for HTTP allowlists
- optional token and secret-path authentication
- same-UID checks for the local control socket
- bounded control input
- named control intents rather than surfacing arbitrary caller text to the agent
- secure service credentials and file modes in LiveKit setup
- previous command-injection and proxy-bypass fixes documented in release history

There are still gaps:

- bearer token comparison uses ordinary string equality rather than a constant-time comparison
- any hook that rewrites arguments across clients is security- and behavior-sensitive and needs contract tests per client
- broad service installers execute privileged package-manager actions and remote installers; those paths need narrow, auditable boundaries

mvx-connect's local-only assumptions reduce network exposure, but the combination of browser gateway, Electron shell, model process control, MCP, and native driver creates a large trust boundary without the same history of adversarial hardening.

**Decision:** retain VoiceMode's security model. Require a threat model for every imported native or browser adapter.

## Specific selections

### Keep in VoiceMode as authoritative

1. **MCP tool and result contracts**
   - `converse`
   - continuation jobs
   - service lifecycle
   - resources and selective tool loading

2. **Provider and model ownership**
   - ordered endpoint configuration
   - local/cloud distinction
   - retry and failover
   - provider-aware model resolution

3. **Coordination and controls**
   - conch and waiter queue
   - pause/resume/stop/skip
   - replay history

4. **Persistence and recovery**
   - conversation/event logs
   - cancellation recovery
   - saved audio and transcript linkage

5. **Portability and operations**
   - macOS/Linux/Windows compatibility
   - launchd/systemd management
   - HTTP bridge
   - self-hosted LiveKit lifecycle

6. **Security boundaries**
   - trusted-proxy model
   - local socket peer authentication
   - fixed control intents
   - loopback/private defaults

### Port or adapt from mvx-connect

1. **Objective latency budgets**
   - time to first audio
   - capture-to-first-partial
   - end-of-speech-to-final-transcript
   - interrupt-to-silence
   - queue/admission time

2. **Truthful readiness**
   - every readiness field tied to a live probe or measured event
   - stale evidence expires
   - simulated evidence clearly labeled and unavailable in production mode

3. **Media journaling**
   - raw capture identity established before optional transforms
   - linked artifacts through enhancement, STT, and conversation logging

4. **Incremental endpointing and barge-in experiments**
   - optional engine capability
   - observable decisions
   - deterministic controls remain available

5. **Speaker-gating experiments**
   - advisory score with explicit failure modes
   - disabled by default
   - never silently discards the only copy of audio

6. **Optional Apple virtual microphone**
   - separate package/component
   - stable versioned ABI
   - truthful latency
   - restart/sleep/wake remapping
   - no hard-coded checkout paths

7. **Browser real-time UX patterns**
   - visible readiness
   - interruptibility
   - direct latency instrumentation
   - clear local-device state

### Reject or defer

1. **Wholesale mvx-connect gateway adoption**
   - duplicates orchestration and product boundaries
   - embeds model and machine topology
   - would regress portability and recovery behavior

2. **Simulated admission/readiness as production state**
   - creates false confidence
   - makes automated recovery choose from fiction

3. **Guardian as an autonomous product policy layer**
   - inferred intent is not a safe replacement for explicit agent/user controls
   - any future version should be advisory and inspectable

4. **Current CoreAudio driver integration**
   - lifecycle, cursor, and latency semantics are not yet trustworthy

5. **Electron as a default application shell**
   - duplicates browser and MCP surfaces
   - adds packaging and update burden without establishing a unique core capability

6. **Apple-only assumptions in VoiceMode core**
   - native Apple acceleration belongs behind an adapter

7. **A second service registry**
   - one canonical provider/readiness model is enough

## Recommended target architecture

The target should have five explicit layers.

### Layer 1: public contracts

Owns:

- MCP tools/resources/prompts
- CLI commands
- stable request/response schemas
- authentication and authorization
- continuation protocol

This layer does not open audio devices or launch models directly.

### Layer 2: conversation coordinator

Owns:

- turn and survey state machines
- cancellation
- continuation
- conch acquisition/release
- control events
- result assembly

It depends on interfaces, not provider modules or sound-device globals.

### Layer 3: media and speech services

Separate interfaces for:

- capture session
- playback session
- STT session
- TTS session
- endpointing
- media journal

The existing local VoiceMode behavior becomes one composition of these services.

### Layer 4: transports and engines

Adapters:

- local sounddevice transport
- LiveKit room transport
- optional mvx-derived low-latency Apple engine
- optional virtual-microphone output

Every adapter reports the same capabilities and event timestamps. Unsupported features are explicit, not silently ignored.

### Layer 5: lifecycle and platform

Owns:

- package installation
- launchd/systemd
- model downloads
- process supervision
- health/readiness evidence
- platform-specific native components

This is the only layer allowed to know filesystem installation layouts.

## Recommended sequence

### Phase 0: restore a trustworthy baseline

Before architectural work:

1. Repair VoiceMode test collection.
2. Run the complete suite and classify every skip:
   - required environment
   - intentionally manual
   - stale test
   - known product defect
3. Fix or remove stale skipped tests that say the code moved or the test needs refactoring.
4. Align the standalone installer with the current CLI.
5. choose one hook implementation and make its behavior match the documented call policy.
6. mark stale architecture docs as historical or rewrite them from current code.

Exit gate: a clean collection, a documented skip budget, and reproducible install/help smoke tests.

### Phase 1: extract contracts without changing behavior

1. Define typed interfaces for:
   - transport
   - recorder
   - player
   - TTS
   - STT
   - control events
   - journal
2. Move result formatting and schema validation out of the operational core.
3. Move provider resolution behind one service.
4. Keep existing local behavior byte-for-byte where practical.

Exit gate: existing tests pass and local `converse` behavior is unchanged.

### Phase 2: make performance observable

Add one event timeline with monotonic timestamps for:

- request accepted
- conch acquired
- provider selected
- TTS request sent
- first audio received
- first audio played
- capture opened
- first speech
- endpoint decision
- STT request/final
- result returned

Do not publish SLO claims until measurements are collected on representative machines.

Exit gate: benchmark output can attribute latency to transport, queue, model, and playback rather than reporting one aggregate.

### Phase 3: prototype an mvx-derived engine adapter

Start with the least invasive capability:

- incremental endpointing and interruption over an adapter interface
- no native driver
- no Guardian autonomy
- no replacement gateway

Run it only on supported Apple hardware and retain the ordinary local transport as fallback.

Exit gate: fallback parity, cancellation parity, and no change for users who do not enable the adapter.

### Phase 4: evaluate the virtual microphone separately

Required before shipping:

- versioned shared-memory header and ABI
- producer and consumer cursor semantics
- atomic ordering documented and tested
- producer restart and remap
- AudioServerPlugIn restart
- sleep/wake
- format negotiation
- truthful reported latency
- overrun/underrun telemetry
- 8+ hour soak
- installer/uninstaller rollback

Exit gate: no stale mapping, no host crash, bounded latency, and recovery without reboot.

### Phase 5: expose only proven features

Public exposure should follow evidence. A capability graduates only after:

- contract tests
- real-device integration tests
- restart tests
- soak tests
- security review
- documented fallback
- operator-visible health

## Evidence gates

### Functional

- scalar speak/listen parity
- survey parity where supported
- cancellation during TTS, playback, capture, STT, and conch wait
- continuation across host deadlines
- provider failure at each stage
- no duplicate microphone opening
- no lost already-captured response

### Real-time

- p50/p95/p99 time to first audio
- p50/p95 endpoint-to-final transcript
- interrupt-to-silence under load
- underrun and overrun counts
- CPU and memory over a long conversation
- latency after sleep/wake and provider restart

### Operational

- cold install
- upgrade
- uninstall
- service crash/restart
- model unavailable
- port occupied by wrong process
- stale socket/lock/shared-memory object
- configuration migration

### Security

- untrusted proxy/header tests
- constant-time bearer-token check
- local socket cross-user rejection
- hook argument rewrite contract per client
- archive extraction traversal/link rejection
- native adapter path and permission review

### Documentation

- every documented command exercised
- every example matched against current `--help`
- architectural claims checked against source
- historical designs clearly labeled

## Current defects and debt that affect the decision

### mvx-connect debt

1. **Readiness and admission are ahead of evidence.** Some states are simulated or assembled from indirect signals. The architecture should not claim production readiness until those states come from live measured dependencies.
2. **The gateway and browser client are overloaded.** Media, policy, process, and UI concerns converge in a small number of central files.
3. **The platform is hard-coded.** Local paths, launch assumptions, Apple-specific binaries, and machine topology appear in operational paths.
4. **The model startup contract is inconsistent.** Server flags, model assumptions, and TTS expectations do not line up cleanly across launchers and callers.
5. **A benchmark imports an obsolete package name.** This weakens confidence in performance evidence.
6. **The CoreAudio latency contract is not truthful.** Zero latency is reported despite buffering.
7. **Shared-memory diagnostics are incomplete.** The consumer-side cursor does not provide authoritative occupancy/overrun state.
8. **Producer restart recovery is under-specified.** A native consumer needs an explicit remap protocol.
9. **Green tests are mostly fast contract/unit evidence.** They do not prove live model, browser, audio-device, or driver behavior.
10. **Product language exceeds implementation maturity.** The repository is strongest when described as a research system.

### VoiceMode debt

1. **The reviewed checkout does not collect tests.** A syntax error in a tracked test prevents the suite from running.
2. **Skipped-test debt is significant.** Reasons include stale paths, removed commands, environment pollution, changed library APIs, missing fixtures, and “needs refactoring.”
3. **Several central modules are too large and multi-purpose.** `converse.py`, `cli.py`, `config.py`, `streaming.py`, and `service.py` are change-amplifiers.
4. **Provider policy is spread across multiple modules.** The operational failover path and registry/model-resolution paths can drift.
5. **LiveKit does not yet have full local-path parity.** Endpoint choice and feature support are narrower.
6. **The standalone installer is stale.** Service command construction, completion setup, documentation references, and command suggestions do not match the current product.
7. **Architecture documentation is stale.** It still describes PyAudio, project config, automatic all-tool loading, Docker deployment, and future plans that do not accurately describe the current tree.
8. **Historical docs are mixed with current guidance.** The archive is valuable, but current readers can easily mistake old architecture for supported behavior.
9. **The modified Rust hook violates a narrow, stable call contract.** It injects `listen_duration_max`, `listen_duration_min`, `vad_aggressiveness`, `disable_silence_detection`, and deprecated `timeout`, including into turn objects. This can override user/server policy and can add keys that the strict turn schema rejects.
10. **Hook implementations and docs disagree.** The docs describe a bash+jq hook that removes a duration override; the inspected Rust path adds multiple overrides.
11. **Bearer token comparison should be constant-time.**
12. **Release history reveals repeated surface churn.** Features have been added, removed, restored, and restructured. The changelog is unusually honest and useful, but the cost is lingering docs/tests/installer drift.

## Counterarguments and defense

### “mvx-connect is cleaner and faster; make it the new core.”

It is cleaner partly because it carries fewer compatibility obligations and targets one hardware topology. Replacing VoiceMode would discard proven behavior in cancellation, continuation, provider failover, multi-agent ownership, HTTP security, lifecycle management, and portability. A faster demo path is not a substitute for those responsibilities.

The right way to capture its performance is an adapter with measured SLOs. If that adapter eventually outperforms and subsumes the local engine, it can become the default based on evidence.

### “Put both repositories together so development is easier.”

A monorepo would not solve the architectural duplication. It would make boundaries less visible and encourage direct imports across experimental and stable code. Shared contracts can live in VoiceMode; the experimental engine can consume them as a separately versioned component until it graduates.

### “VoiceMode is too tangled; starting over is cheaper.”

VoiceMode is tangled, but much of the complexity encodes failures already encountered in real use: cancellation scopes, stale conch grants, provider incompatibility, service restart behavior, proxy spoofing, command injection, audio truncation, package drift, and host deadlines. A rewrite would rediscover these unless the contracts and tests are carried forward.

Refactoring behind stable behavior is lower risk than replacing the system with a prototype.

### “The mvx native driver is the differentiator; ship it now.”

A virtual microphone can be differentiating, but AudioServerPlugIn and shared-memory lifecycle errors affect unrelated host applications. Cursor ownership, remapping, truthful latency, and restart behavior are prerequisites, not polish. Shipping it separately also makes failure and rollback much safer.

### “Guardian should decide when to interrupt and who gets to speak.”

Semantic inference can improve endpointing, but deterministic ownership and explicit controls are more reliable for arbitration. Guardian-like outputs should be evidence with confidence and provenance. They should not become silent authority over whether captured speech is discarded or which agent owns the channel.

### “VoiceMode already has LiveKit, so mvx contributes nothing.”

The transports optimize different things. LiveKit supplies rooms, browser interoperability, and managed media transport. mvx-connect demonstrates a tighter local direct loop and treats latency/endpointing as primary architecture. Its contribution is the real-time design pressure and instrumentation model, not necessarily its wire protocol.

## Final recommendation

Use **VoiceMode as the durable product spine** and **mvx-connect as a constrained real-time R&D source**.

The first engineering investment should not be a feature port. It should be restoring a trustworthy VoiceMode baseline and creating boundaries that can accept an alternative engine without duplicating the product:

1. green collection and explicit skip accounting
2. installer and hook contract repair
3. current architecture documentation
4. conversation/media/provider interfaces
5. monotonic end-to-end instrumentation

Then port mvx-connect ideas in this order:

1. latency/readiness instrumentation
2. media journaling
3. optional incremental endpointing and barge-in
4. browser UX improvements
5. native virtual microphone only after independent hardening

This recommendation preserves what each repository has actually earned:

- VoiceMode has earned ownership of contracts, recovery, security, lifecycle, and portability.
- mvx-connect has earned a place as the source of aggressive real-time and native-audio experiments.

Combining those strengths requires an interface and evidence program, not a codebase merger.
