---
name: VoiceMode Reliability Observation
status: active
source: /Users/ibhatt/.cursor/plans/voicemode_reliability_audit_79e6e2ac.plan.md
updated: 2026-09-07
---

# VoiceMode Reliability Observation and Repair

## Locked decisions

- Run and document stock PyPI VoiceMode 8.12.0 before deciding where any
  continuation clock starts or how cutover works.
- Do not modify stock TTS during observation.
- State every mutating command, expected effects, and rollback before running
  it. Installation and service checks happen collaboratively, one checkpoint
  at a time.
- Keep stock 8.12.0 as the baseline.
- Before installing repository code, give the development build a distinct
  version/build identity through repository tooling and install it through a
  separate environment, executable, and MCP entry. A version label alone is
  insufficient because it would still collide on `voicemode` in `PATH`.
- Keep VoiceBridge until native continuation passes the agreed live tests.

## Phase 1: Observatory window

Create a dated observation ledger under `_inspect` containing:

- exact command;
- expected behavior and side effects;
- actual output;
- affected paths, processes, ports, and logs;
- verdict and confirmed defect;
- rollback or cleanup required.

Seed it with already observed facts:

- stock PyPI 8.12.0 is the active executable and has no continuation manager;
- the workspace is not yet a Git checkout and contains prior modified source;
- Whisper is still running on 2060 from files moved under Trash;
- current launchd entries target missing Whisper, Kokoro, and MLX executables;
- stock recreates a literal workspace `~/.voicemode/logs/events` tree because
  `EVENT_LOG_DIR` skips path expansion;
- the documented and implemented service/model command surfaces disagree.

No continuation implementation decision is made during this phase.

## Phase 2: Collaborative stock reproduction

For Whisper, Kokoro, MLX Audio, and VoiceMode Serve:

1. Inspect the supported command and configuration surface.
2. Predict generated files, process changes, bind port, health/status port,
   provider URL, model, and restart behavior.
3. Ask the user to run or approve the command.
4. Capture the actual result in the ledger.
5. Stop after any mismatch and diagnose it before the next command.

Required reproductions include:

- canonical `service install` dropping service-specific model/port arguments;
- Whisper template placeholders and health checks;
- `large-v3-turbo` installation and activation;
- Kokoro generating a custom-port script but ignoring it in the plist;
- MLX Audio failing to persist installer port configuration;
- Serve using configured runtime port but hardcoded lifecycle port;
- service bind ports drifting from STT/TTS provider URLs;
- global/project configuration precedence and `export KEY=value` handling;
- literal-tilde path creation.

The existing orphaned Whisper process and stale launchd entries are not stopped
or rewritten without a dedicated approval checkpoint.

## Phase 3: Review evidence and choose continuation semantics

Measure stock behavior before designing:

1. Assistant TTS longer than 60 seconds.
2. A subsequent `listen_duration_max=55` recording.
3. Configured/default listen duration behavior.
4. An explicitly supplied listen duration above 60 seconds.
5. Cursor MCP request timing and cancellation evidence.

Then decide together:

- eligibility based on effective listen duration;
- phase where observation/cutover begins;
- numerical cutover budget;
- scalar versus survey behavior;
- explicit cancellation and transport-close behavior;
- how the host automatically invokes continuation.

The immutable core requirement is that continuation resumes the same
server-owned operation and never opens a second microphone.

## Phase 4: Establish development identity

Before any source install:

- establish the clean Git repository baseline;
- compare and selectively reapply the prior bundle;
- choose a development version using project/release tooling rather than
  silently masquerading as stock 8.12.0;
- install into an isolated environment;
- expose a distinct command such as `voicemode-dev`;
- register a separate MCP entry such as `voicemode-dev`;
- verify both stock and development versions independently before testing.

Do not overwrite the stock `voicemode` executable.

## Phase 5: Implement confirmed repairs

Likely files, subject to the observation review:

- `voice_mode/config.py`
- `voice_mode/cli.py`
- `voice_mode/tools/service.py`
- `voice_mode/tools/whisper/install.py`
- `voice_mode/tools/kokoro/install.py`
- `voice_mode/tools/mlx_audio/install.py`
- service launcher templates
- `voice_mode/tools/converse.py`
- the continuation job manager
- focused tests and current documentation

Service configuration must have one source of truth from configuration command
through generated launcher, actual bind port, lifecycle health/status, provider
endpoint, and restart.

## Phase 6: Verification

- Run tests with an isolated `VOICEMODE_BASE_DIR`, mocked lifecycle operations,
  and audio disabled.
- Repeat the stock long-TTS/55-second-listen test against the distinct
  development build.
- Exercise the jointly approved continuation case and recover the transcript
  from the same recording.
- Install and run each service collaboratively; verify port, endpoint, model,
  generated target, restart persistence, and saved transcription.
- If stock TTS is cancelled before listening starts, pause and revisit the
  protocol before touching TTS code.

## Phase 7: Remove workaround and prepare PR

- Remove/deactivate VoiceBridge only after native continuation succeeds.
- Update CLI, installation, environment, model, port, and troubleshooting docs.
- Turn every confirmed observation into a regression test where practical.
- Maintain `CHANGELOG.md` under Unreleased.
- Review a clean Git diff and prepare the PR only after final user approval.
