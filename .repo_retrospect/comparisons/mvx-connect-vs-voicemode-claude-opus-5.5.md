# mvx-connect vs voicemode: comparison, selections, and decisions

Author: Claude Opus 5.5 (Cursor agent)
Date: 2026-10-02
Repositories:

- `/Users/ibhatt/git/git-personal/mvx-connect` (read first, end to end)
- `/Users/ibhatt/my_local_share/voicemode` (read second)

Nothing was committed and no product code was edited in either repository. The
only scratch files I created live in `/tmp`.

---

## 1. Bottom line

1. **voicemode is the base.** It is the only one of the two that closes the
   loop an agent actually needs: the agent calls a tool, the user hears speech,
   the user answers, and the agent gets text back. mvx-connect never closes that
   loop. None of its 19 MCP tools speaks or listens, and its primary realtime
   transcripts never reach the MCP side at all (verified, section 4).
2. **Retire mvx-connect as a product, and harvest four specific things from
   it.** They are the streaming-STT bridge pattern, the semantic end-of-turn
   rule, the "what the user actually heard" interruption contract, and the
   MLX threading lessons. Everything else should stay behind. That includes the
   CoreAudio virtual microphone, the guardian LLM, the readiness and evidence
   machinery, speaker enrollment, the 19-tool contract surface, the Electron
   shell, and the branding layer. Section 6 gives the reason for each item.
3. **Fix voicemode's fork hygiene before adding features.** The LICENSE file
   was deleted. A global `mbailey` → `IB-QA` replace misattributed the original
   author's words and broke a test file and the release script. 13 tests fail
   and one test file does not compile (section 5).
4. **Put full duplex and voice barge-in on the LiveKit/WebRTC transport, not on
   a custom gateway.** Barge-in from open speakers needs echo cancellation.
   WebRTC gives you echo cancellation, and voicemode already has a loopback-only
   LiveKit transport. mvx relied on the browser's echo cancellation for the same
   reason. Rebuilding that in a bespoke FastAPI WebSocket gateway is the wrong
   place to spend effort.
5. **mvx's own product vision is better served by voicemode.** mvx's VISION
   note describes an agent handing off "a script plus pacing" for a spoken
   presentation. voicemode's `turns[]` already does most of that: ordered
   multi-voice `say`/`ask` turns, `pause_after_ms`, durable per-turn reply
   capture, conch floor control, and `converse_continue` for long runs. mvx has
   no code for it.

---

## 2. Method and coverage

### What I read

**mvx-connect** (143 tracked files, about 22k lines including lockfiles, 5
commits, last commit 2026-07-03). I read every source module in full: CLI,
TUI, package commands, readiness, every `mcp/` file, every `gateway/` file
including the browser client (`index.html`, `app.js`, worklet, widget), every
`guardian/`, `turn/`, `media/`, `models/`, `bench/`, and `driver/` file. I
also read the C HAL driver (`MVXVoice.c`, `mvx_ring.h`), its Makefile, plist,
install scripts, README, and DESIGN; the watchdog daemon; all three launchd
plists; the install/uninstall/model-server scripts; and the Electron shell.
For docs I read README, VISION, HANDOFF, CLAUDE.md, and the RUNBOOK, plus the
text of both branding HTML documents. I enumerated every test, read the
load-bearing ones in full (gateway app, writer, conftest), and ran the suite.

**voicemode** (482 tracked files, 2,166 commits). Here I read the central
runtime path in full or near full:

- `server.py`
- the `converse` tool, its parameter handling, the recording/VAD loop,
  `listen_and_transcribe`, the cancellation recovery, the turns pipelines, and
  the continuation wiring
- `simple_failover.py`, `conversation_jobs.py`, the tool loader
- the LiveKit `transport.py` and the new uncommitted `native.py`
- the `serve` command, and the mlx-audio installer header and version pins

For the rest of the package, I outlined every module with its docstrings and
read targeted sections. That covers conch, the conch queue and ops, the control
channel and socket, history buffer, reconnect, the MCP launcher and bridge, the
serve middleware, core, streaming, providers, provider discovery, config (all
1,441 lines outlined, environment variables counted), the CLI (2,294 lines
outlined), every `cli_commands/` module, and every `tools/` module.

I also read:

- README, `pyproject.toml`, and AGENTS.md (identical to CLAUDE.md)
- the plugin and hook config files (`.claude-plugin`, `.cursor/hooks.json`,
  `.claude/settings.json`, `apm.yml`)
- the CI workflow
- the doc index and section maps
- `.repo_retrospect/` STATE, FINDINGS, plans, and observations
- the first page of the committed PDF
- the full uncommitted diff

I ran the test suite.

I did **not** read every line of `docs/.archive/` (70 files of historical
notes), the 2.4 MB compiled `voicemode_hook` binary, or the minified LiveKit
frontend bundle. Where a claim rests on code reading rather than execution, I
say so.

### What I deliberately did not read

`.repo_retrospect/comparisons/` already holds `gpt-5.6-sol` and `grok-4.7`
versions of this comparison. There was also an earlier `claude-opus-5.5` file
at this exact path, written at 04:10 today by another run. I did not open any
of them, so my judgment would not anchor on theirs. I backed up the earlier
file at this path to `/tmp/mvx-connect-vs-voicemode-claude-opus-5.5.prior-run-0410.md`
before replacing it.

### Fresh evidence I produced

| Check | Result |
|---|---|
| mvx test suite (`.venv`, Python 3.14) | 248 passed, 2 skipped (DeepFilterNet needs `torchaudio`, isolation needs `speechbrain`; neither is installed or declared), 1.3 s |
| voicemode test suite (`-n 8 --no-cov`) | 1,434 passed, **13 failed**, 60 skipped, plus **1 collection error** (`tests/test_provider_selection.py` is a `SyntaxError`), 22 s |
| mvx realtime transcripts visible to MCP? | **No.** A fake realtime session produced `transcript.final` over the WebSocket. `GET /sessions/rt1/transcripts/latest`, which backs the MCP tool, returned `[]`, and zero files were spooled. |
| mvx virtual-mic speech gate on 10 ms blocks | **10 of 32** loud speech blocks accepted (Silero needs 512-sample chunks; the writer feeds 160). About two thirds of speech is zero-filled. |
| mvx DeepFilterNet output ordering on 10 ms blocks | First 9 blocks pass through raw, then model output, then one raw block inserted out of sequence at block 19. Audio is duplicated and reordered at startup. |
| `mvx mcp --gateway-url …` | Fails with `mvx: error: unrecognized arguments: mcp` (the subcommand re-parses `sys.argv`) |
| MCP tool surface | mvx exposes 19 tools totaling about 11.6k characters of schema; none perform voice I/O. voicemode's default load is 4 tools totaling about 20.3k characters, of which `converse` alone is about 16.6k (roughly 4k tokens). |
| mlx-audio realtime route | The local upstream checkout's `v0.4.3` tag contains `@app.websocket("/v1/realtime")`. voicemode pins `mlx-audio>=0.4.3,<0.4.4`, so the streaming STT that mvx used is probably already reachable from voicemode's managed service. This still needs confirming against the PyPI wheel. |

---

## 3. What each repository actually is

### mvx-connect (package `mvx`, "mV Connect X / I.R.I.S.")

A Mac-only realtime speech prototype built in about one week (June 27 to July
3, 2026), with five layers.

1. **Realtime gateway (FastAPI).** The browser page captures the mic with
   browser echo cancellation, noise suppression, and gain control, downsamples
   to 16 kHz PCM16, and streams 20 ms frames over a WebSocket. The server runs
   an enhancer, then an optional Silero/WebRTC gate, then Voxtral realtime STT
   deltas. Semantic endpointing either holds the turn or finalizes it, with a
   4.5 s hard cap. Kokoro TTS is a one-shot WAV per utterance. All MLX work is
   pinned to one executor thread. An optional remote mode bridges to
   `mlx_audio.server`'s OpenAI-Realtime WebSocket instead of loading Voxtral
   in-process.
2. **Interruption intelligence.** `PlaybackTracker` splits the assistant's
   text into played and unheard parts from the played milliseconds.
   `IntentInferenceEngine` defers a "why did they interrupt" briefing until the
   user's follow-up turn finalizes. `GuardianAngel` pushes unsolicited
   goal-alignment "whispers", optionally written by a local Qwen2.5-1.5B.
3. **MCP control plane.** 19 tools. They return contracts and dry-run plans:
   session descriptors with hardcoded `ws://127.0.0.1:8766` URLs, install and
   service plans, model matrices, and readiness reports. They never move audio
   or text between the user and the agent.
4. **System-wide virtual microphone.** A Core Audio HAL plug-in in C reads a
   lock-free shared-memory ring. A Python writer captures the real mic and runs
   DeepFilterNet3, then a speech gate, then ECAPA speaker isolation, then writes
   to the ring. The goal is a Krisp/Teams-style "only my voice" mic.
5. **Evidence and readiness scaffolding.** About 1.5k lines of admission
   gates, latency budgets, duplex-loop invariants, spoken-response policy,
   conversion policy, source facts, failure recovery, and a simulated benchmark
   harness. The readiness verdict is computed from hardcoded "not executed"
   inputs, so it is "blocked" by construction and never consumes real runtime
   measurements.

On top of this sit an Electron tray shell, an Adaptive Card widget, a watchdog,
and a large brand narrative: I.R.I.S. "finds you", TETHERMATRIX "parallel
pipelines, nothing is skipped", and routing to your phone. None of those
promises exist in code.

### voicemode (private working clone of `mbailey/voicemode`, version `8.12.9+ib`)

A mature, half-duplex agent voice tool with heavy operations infrastructure.

- **The `converse` tool.** It speaks via streaming TTS over OpenAI-compatible
  endpoints (whisper.cpp, Kokoro, mlx-audio, OpenAI, Cartesia), records with
  WebRTC VAD silence detection, transcribes in one batch request with failover
  and transient retry, and returns the text.
- **Robustness around host realities.**
  - `converse_continue` jobs work around the roughly 60 s MCP call deadline in
    hosts like Cursor.
  - Cancellation (ESC) recovery saves and transcribes partial audio without
    tearing down the server.
  - A control channel (Unix socket with peer-uid check) supports pause,
    resume, stop, skip-back replay from a history buffer, and skip-forward as a
    manual end of turn; media keys and Hammerspoon drive it.
  - Multi-agent floor control ("conch") has a FIFO queue, wait and callback
    modes, hold TTLs, and CLI/MCP parity.
- **`turns[]`.** Ordered multi-voice `say`/`ask` sequences with per-turn
  pacing, synthesis lookahead (turn N+1 is synthesized while turn N plays), and
  durable per-reply logging.
- **Services and installers.** whisper.cpp, Kokoro, mlx-audio (with a bundled
  upstream patch and a deliberate `<0.4.4` pin to avoid a Kokoro decoder crash),
  and LiveKit (checksummed binary, loopback-only). launchd and systemd
  templates. A `serve` HTTP mode with an IP allowlist, trusted-proxy handling,
  and bearer token. A plugin installer that merges user-level hooks and MCP
  config across seven clients.
- **LiveKit transport.** Optional and loopback-enforced. It handles one
  exchange per call (join, `say`, wait for the first final transcript, leave),
  plus a new, uncommitted "native join as human" mode.

---

## 4. Assessment of mvx-connect

### What is genuinely good

- **The remote realtime session adapter** (`gateway/remote_realtime.py`). It
  is a clean drop-in that satisfies a synchronous `feed`/`step`/`close`
  protocol by marshaling onto a background event loop that talks to
  `/v1/realtime`. It isolates heavy MLX models from the gateway process and
  lets the model live in one long-running server. This is the right shape for
  streaming STT behind an agent tool.
- **Conservative semantic endpointing** (`turn/semantic_endpoint.py` plus
  `finalize_turn` in `gateway/app.py`). After client-side silence, it finalizes
  only when the text looks complete (final punctuation, or at least 4 words not
  ending on a continuation word like "and" or "the"). Otherwise it holds, up to
  a hard cap. It is small, deterministic, and addresses the "it cut me off
  mid-thought" failure directly.
- **The "what the user actually heard" contract** (`gateway/barge_in.py`).
  Given played milliseconds over total milliseconds, it splits the text at a
  word boundary into `playedText` and `remainingText`. Any agent benefits from
  knowing which part of its answer was never heard.
- **Hard-won MLX knowledge.** Metal streams are thread-affine: stepping a
  session on another thread raises "There is no Stream(gpu, N)". Overlapping
  sessions crashed command buffers. The mlx-audio Kokoro `istftnet` crash is
  noted too, and voicemode independently pinned around the same crash.
- **Truthful provider metadata.** Every enhancer reports `modelBacked`,
  `applied`, and `fallbackReason` instead of pretending.
- **The ring ABI discipline.** The C `_Static_assert` offsets are mirrored in
  Python and verified by a test that compiles a C probe. As an engineering
  exercise it is careful work.

### What is broken or misleading (all verified in code; probes in section 2)

1. **The agent loop is not closed.**
   - Realtime transcripts exist only as WebSocket events to the browser.
     `voice_gateway_latest_transcripts` reads `transcripts.jsonl`, which only
     the legacy chunk path writes. An agent using mvx over MCP cannot hear the
     user on the primary path.
   - Nothing feeds agent text into TTS either. The only "assistant speech" is
     a hardcoded demo sentence behind a "Mark Assistant Speaking" button, sent
     with a hardcoded `totalAudioMs: 4200`, so the barge-in split is computed
     against a fake duration.
2. **The "durable, nothing is lost" promise is false for the primary path.**
   The realtime WebSocket spools nothing to disk. The watchdog's live-session
   detector looks for spooled audio files, so it cannot see realtime sessions
   and could restart the gateway mid-conversation.
3. **The virtual microphone would not work as shipped.** By code reading, with
   two defects confirmed by probe:
   - The gate decides per 10 ms block, but Silero needs 512 samples. Blocks
     without a full chunk return "not speech" and get zero-filled. In the probe,
     10 of 32 loud speech blocks passed.
   - DeepFilterNet and the isolator return raw audio during warm-up and then
     buffered model output. That duplicates about 90 ms at start and inserts
     raw blocks out of order.
   - The writer recreates the shared-memory segment on every restart (unlink,
     then create). The driver re-maps only while its pointer is NULL, so after a
     writer restart under launchd KeepAlive the driver stays attached to the
     orphaned segment and is silent until `coreaudiod` restarts. DESIGN.md
     claims reconnect via an epoch check, but an epoch check cannot detect a
     new segment object.
   - The writer creates the segment as mode `0600`, owned by the login user.
     `coreaudiod` runs as `_coreaudiod` inside a sandbox, so `shm_open(O_RDONLY)`
     will very likely fail with a permission error. I did not test this on
     hardware.
   - The driver advertises zero latency and zero safety offset, its clock is
     free-running with no drift correction, and the bundle is unsigned.
4. **The guardian contradicts the project's own MLX rule and competes with
   STT.** `LocalGuardianLlm` runs on its own `mlx-guardian` thread and holds
   `MLX_REALTIME_LOCK` for a full 220-token generation. It fires automatically
   every 2 turns or 25 s, so while it generates, every realtime `feed`/`step`
   waits. That is a recurring multi-second transcription stall by design.
5. **Dependencies don't match the defaults.** The installer's default enhancer
   is `deepfilternet+isolation`, but `pyproject.toml` declares neither
   `deepfilternet`/`torch`/`torchaudio` nor `speechbrain`. A fresh install
   silently falls back to the adaptive RMS gate while the UI shows "Voice Lock".
   `mlx_audio` is not in the dev environment either, so **no test ever touches a
   real model**.
6. **The evidence machinery is process theater.** Readiness, admission,
   latency trace, duplex loop, spoken policy, conversion policy, failure
   recovery, and the simulated benchmark all evaluate hardcoded or simulated
   inputs. The tests confirm the gates block when told to block. The real
   numbers (0.48 s first delta, 0.18 s warm Kokoro) appear only in prose, and
   the files that supported them were untracked in commit `acc3cc5`.
7. **Smaller defects:**
   - `mvx mcp` is broken.
   - `bench/denoise_rtf.py` imports the pre-rename `mlx_voice_agent` package.
   - `/transcribe` claims non-English uses Qwen3 but always passes
     `--language en`.
   - The widget emits a `voice_widget_action` tool call that doesn't exist.
   - `mcp/contracts.py` still says `mcpSdkInstalled: False`.
   - Every live STT chunk spawns a fresh `python3 -m mlx_audio.stt.generate`
     subprocess, so each chunk cold-loads the model.
8. **Documentation drift.**
   - The test count is listed as 129 in HANDOFF and RUNBOOK, as "234+" in
     CLAUDE.md, and is 248 in reality.
   - README lists 7 tools; the server has 19.
   - The branding document defines `mvx chat` as the one-off exchange and
     `mvx connect` as the bounded link, while the code makes `voice_connect` the
     one-off and `voice_chat` the long-running one.
   - The browser logo still reads "QA", and `CLAUDE.md` points to a
     `runtime/mcp_probe.py` that does not exist.
9. **Security posture.**
   - The gateway has no authentication: mic streaming, TTS, voiceprint
     enrollment and reset, and transcription are all open.
   - The runbook recommends exposing it through a Cloudflare tunnel hostname.
   - The watchdog defaults to `launchctl kickstart -k` on voicemode's own
     labels (`com.voicemode.kokoro`, `com.voicemode.mlx-audio`). If both stacks
     are installed, mvx will restart voicemode's services.
   - The branding HTML hot-links `AnthropicSans` font files from
     `assets.claude.ai`.

### Net

mvx-connect is a promising streaming-STT experiment wrapped in a much larger
amount of unfinished scope. Roughly 30% of its code is load-bearing for
realtime speech. The other 70% is scaffolding, adjacent products (virtual mic,
oversight LLM, desktop shell), or narrative.

---

## 5. Assessment of voicemode

### What is genuinely good

- **It works end to end for the job that matters.** The agent speaks, listens,
  and gets text back, across hosts, platforms, and providers.
- **It is built around real host failure modes.** Every one of these exists
  because something broke in the field:
  - Host deadlines are handled by continuation jobs.
  - ESC cancellation is handled by `stop_event` plus a recovery thread that
    owns its own event loop.
  - Orphaned queue waiters are deregistered on every exit path (VM-1967).
  - Local whisper.cpp timeouts are retried by classified transient retry.
  - Device loss is handled by re-initializing sounddevice.
- **The defaults are restrained.** Only `converse` and `service` load unless
  the user opts in to more tools.
- **The security work is sound.**
  - The `serve` IP allowlist honors `X-Forwarded-For` only from trusted
    proxies (there's a GHSA reference).
  - The bearer-token middleware is in place.
  - LiveKit rejects insecure URLs off loopback.
  - The browser token travels in the URL fragment and is scrubbed from history.
  - The control socket checks the peer uid.
  - Job files are written `0600` with atomic replace.
- **Operational knowledge is encoded in code.** Version pins carry reasons,
  the mlx-audio patch is applied idempotently with a sentinel, and services are
  checked against the port rather than the exit code.
- **The test investment is large.** About 1,500 tests with deterministic
  fakes. The failures are hygiene problems (below), not logic failures.

### What is weak

1. **Half duplex only.**
   - It records the whole utterance, then uploads it for one batch
     transcription. The latency floor is the silence threshold plus encode, plus
     upload, plus full transcription.
   - There is no streaming STT, no voice barge-in, and no echo cancellation;
     "barge-in" means control-channel keys.
   - Capture runs at 24 kHz and each 30 ms chunk is FFT-resampled to 16 kHz for
     VAD.
2. **Interface sprawl.** `converse` takes 31 parameters, and the config layer
   reads 108 `VOICEMODE_*` variables (169 across the package).
   - Agents misuse the timing and VAD knobs. You responded with a Cursor rule
     ("pass only `message`, `wait_for_response`, `hold_conch`") and a Rust
     PreToolUse hook that rewrites `listen_duration_min`, `vad_aggressiveness`,
     `disable_silence_detection`, and `timeout` on the way in. When a client-side
     hook has to correct the server's own schema, the schema is wrong.
   - The repo already contains a "minimal tool description" proposal (about 250
     tokens, versus about 4,000 today) that was never adopted.
   - The docstring injects behavioral instructions into every host (a
     "BLOCKING REQUIREMENT" to invoke skills, plus mandatory echo formatting).
     Hosts treat that as prompt content.
3. **Module size.** `tools/converse.py` is 4,637 lines, `_converse_core` alone
   is about 1,400 lines, and its roughly 170-line docstring is duplicated
   verbatim between `converse` and `_converse_core`.
4. **Fork hygiene is currently broken.**
   - **`LICENSE` was deleted** in `62b4947` ("remove stale repo metadata").
     The project is MIT-derived from `mbailey/voicemode`, and MIT requires the
     copyright and permission notice to ship with copies. This is the most
     serious item in either repository.
   - **The global rename in `d824a83` rewrote "mbailey" to "IB-QA" across code
     and tests.** Comments that quote the original author ("IB-QA's hard
     constraint", "the exact bug IB-QA reported") now attribute his words to you.
     It also produced `def test_global_set_to_mlx_repo_id_IB-QAs_env`, a
     `SyntaxError` that stops collection of that test file, and broke
     `scripts/release.py` canonical-remote resolution (3 failing tests). Because
     `make release` pushes through that resolver, the release path is suspect.
   - **Stale tests and config.** 9 tests target the removed
     `converse-pre-tool-use.sh`. `.claude/settings.json` points at that deleted
     script and the deleted `voicemode-hook-receiver`; `|| true` hides the
     failure.
   - **Committed artifacts.** The repo carries a 2.4 MB compiled hook binary
     with no build-reproducibility check, an IEEE-copyrighted paper
     (`2509.00078v2.pdf`, Apple's ChipChat) whose notice forbids
     redistribution, an absolute `/Users/ibhatt/...` path in
     `.cursor/hooks.json`, and an unrelated APM dependency
     (`pm-skills-arsenal`) wired into `.github/mcp.json`.
   - **URLs.** The README and `pyproject.toml` use a malformed URL
     (`IB-QA/voice-patchvoicemode`), while `git remote` says `IB-QA/voice-patch`.
5. **Fragile recovery tool.** `reconnect.py` heals a dropped MCP server by
   driving Claude Code's `/mcp` TUI through tmux and scraping the screen. That
   breaks on any UI change.
6. **Uncommitted work-in-progress risks.**
   - `listen_and_transcribe` now reads `loop._default_executor`, a private
     asyncio attribute.
   - Native LiveKit join claims to "play subscribed audio", but nothing
     subscribes to or plays remote tracks explicitly; whether
     `rtc.PlatformAudio` does that implicitly is unverified, and the tests use
     fakes.
   - The LiveKit transport reconnects and builds a new `AgentSession` on every
     `converse` call and returns only the first final transcript.

---

## 6. Selections: what to keep, harvest, fix, and drop

### Decision criteria (applied to every item)

1. **Does it serve the agent ⇄ human voice loop?** That is the product both
   repositories exist for.
2. **Is it proven by execution, or only by assertion?**
3. **What does it cost to carry,** in dependencies, privileges (sudo, HAL,
   signing), surface area, and token budget?
4. **Does a maintained platform already solve it?** That covers LiveKit/WebRTC,
   mlx-audio, BlackHole/Krisp, and the OS echo-cancellation stack.

### Harvest from mvx-connect into voicemode

| # | Item | Source | Why it qualifies | Acceptance gate before merging |
|---|---|---|---|---|
| H1 | **Streaming STT via mlx-audio `/v1/realtime`** as an optional listen backend | `gateway/remote_realtime.py` | Criterion 1 directly: it cuts the end-of-speech-to-text latency floor. voicemode already installs and pins the mlx-audio service on 8890, and the `v0.4.3` tag appears to contain the route, so there is no new service and no new model server. | Benchmark on the same 20 recorded utterances with the current batch path and with the streaming path. Ship it only if the median end-of-speech-to-text time improves by at least 300 ms with no word-error regression. Default off. |
| H2 | **Semantic end-of-turn hold** combined with VAD silence | `turn/semantic_endpoint.py` and the hold/finalize logic in `app.py` | It addresses "cut off mid-thought" without exposing more knobs. It also lets voicemode stop asking agents to tune `listen_duration_min`. | Unit tests carried over. A replay of real transcripts shows fewer premature cutoffs at equal or lower added latency. The 4.5 s hard cap stays as a server constant, not a parameter. |
| H3 | **Heard/unheard split** in results after a control-channel stop or skip-forward | `gateway/barge_in.py` | voicemode's streaming player knows the samples it played, so it can report exactly which words the user heard. That makes the agent's next turn correct, and it is the prerequisite for any future voice barge-in. | Played duration comes from the real sample counter, not a constant. Covered by a test on `stream_pcm_audio` with an injected stop. |
| H4 | **MLX threading rule and pitfalls** as documentation | `CLAUDE.md` gotchas and `_MLX_EXECUTOR` comments | It is free and prevents a known crash class if voicemode ever runs MLX in-process. The current advice is to keep MLX in the mlx-audio server. | A troubleshooting note in voicemode's docs. |

Explicitly **not** harvested: the bespoke realtime WebSocket gateway as a
whole. Its value is H1 to H3, and the transport itself is better provided by
LiveKit (decision D5).

### Drop from mvx-connect (and the driver behind each)

| Item | Driver for dropping |
|---|---|
| Core Audio HAL virtual mic and writer | It is a different product (a system-wide denoised mic for Zoom/Teams). It needs sudo, a signed and notarized bundle, and sandbox-compatible IPC. It ships with 4 or more blocking defects (section 4, item 3). BlackHole plus Krisp-class tools already exist. If you want this product, start it as its own repository with the ring-buffer ABI as the seed. |
| Guardian angel and intent-inference LLM | It is tangential to the voice loop, competes with STT for the MLX lock by design, and its deterministic fallback is keyword overlap. The main agent already holds full context; a 1.5B side model second-guessing it adds latency and noise. |
| Readiness, admission, and evidence modules plus the simulated harness | They measure nothing real. Replace them with one real benchmark script (see R4). |
| The 19-tool MCP surface | The tools return contracts, not capability. They would inflate the host's tool budget for no I/O. |
| Speaker enrollment and ECAPA isolation | Experimental (the docstring says so), heavy undeclared dependencies, 0.5 s analysis windows that add latency, and a risk of silencing the real user. Reconsider only alongside a WebRTC path with real separation models. |
| Electron shell and Adaptive Card widget | They wrap a UI that has no agent behind it. |
| Watchdog | It restarts voicemode's services by label and cannot see realtime sessions. voicemode's service layer already checks health against the port. |
| Brand narrative (I.R.I.S., TETHERMATRIX) | Its promises (parallel redundant pipelines, phone routing, "nothing is skipped") have no implementation. Keeping the name keeps the expectation. |

### Fix in voicemode (ordered)

- **R0. Licensing and attribution (blocking).**
  - Restore `LICENSE` with the original MIT notice; add your own copyright line
    if you like, but keep the original.
  - Revert the `IB-QA` substitutions inside attribution comments and test
    docstrings, keeping them only in URLs and metadata that really refer to your
    fork.
  - Fix the corrupted identifier.
  - Remove `2509.00078v2.pdf` from the tree; link it instead.
- **R1. Get to green.**
  - Fix `scripts/release.py` remote resolution (canonical owner/repo versus the
    actual `voice-patch` remote).
  - Delete or retarget the 9 stale shell-hook tests to the Rust binary.
  - Fix `.claude/settings.json`.
  - Replace the absolute path in `.cursor/hooks.json` with one the plugin
    installer writes.
  - Decide whether the hook binary is built in CI (preferred) or committed with
    a checksum test against `Cargo.lock` and source.
  - Correct the README and `pyproject.toml` URLs.
- **R2. Shrink `converse`'s public schema.**
  - Adopt the existing minimal-description proposal.
  - Keep `message`, `turns`, `wait_for_response`, `hold_conch`, `voice`,
    `transport`, `session_id`, and `continuation_wait` public.
  - Move the timing and VAD knobs (`listen_duration_*`, `vad_aggressiveness`,
    `disable_silence_detection`, `timeout`, chime silences) to configuration,
    and accept-but-ignore them for backward compatibility, with a logged
    warning.
  - Remove behavioral instructions (the skills "BLOCKING REQUIREMENT", echo
    mandates) from the schema and move them into the voicemode skill.
  - This makes your Cursor rule and the parameter-rewriting half of the Rust
    hook unnecessary, because the server enforces the policy itself for every
    client.
- **R3. Split `converse.py`.** Parameter normalization, recording/VAD, STT
  orchestration, the turns pipelines, and conch orchestration become separate
  modules behind the existing `ListenResult` seam, with no behavior change.
- **R4. One real latency benchmark.** Replay fixed WAV files through each
  listen backend and each TTS provider, record end-of-speech-to-text and
  text-to-first-audio time, and write JSONL. This replaces mvx's simulated
  harness and gates H1 and H2.
- **R5. Harden the uncommitted LiveKit and recovery work.**
  - Replace `loop._default_executor` with an owned module-level executor.
  - Add a real-device test, or at least a documented manual check, that native
    join plays remote audio.
  - Keep one `AgentSession` per room for the conversation instead of per call
    (that also removes per-turn connect latency).
- **R6. Replace tmux screen-scraping reconnect** with a documented manual step,
  or keep it but label it best-effort Claude Code only, since it depends on an
  external UI.

---

## 7. Decisions and how I defend them

### D1. voicemode is the base; mvx-connect does not continue as a product

- **Driver:** criterion 1. voicemode closes the loop; mvx does not. On top of
  that, voicemode has about 2,000 commits of field-driven hardening and 1,400+
  passing tests, against mvx's week-old prototype whose tests never touch a
  model.
- **Counterargument:** "mvx has the better audio pipeline (streaming STT,
  semantic endpointing, enhancement)." True. But that pipeline is a few hundred
  portable lines (H1 and H2). What remains is unfinished scope that would have
  to be fixed before it could be relied on, and the loop it lacks is the hard
  part voicemode already solved.
- **Counterargument:** "voicemode has fork and licensing problems." Those are
  mechanical and fixable in a day (R0, R1). mvx's gaps are architectural.

### D2. Harvest exactly four items, each behind a measurable gate

- **Driver:** criterion 2. mvx's best numbers live only in prose, so nothing
  enters voicemode without a reproducible benchmark (R4). Merging code
  wholesale would import the guardian's lock contention, the undeclared
  dependencies, and the evidence theater.
- **Defense:** H1 is nearly free, because voicemode already runs the server
  that provides `/v1/realtime`. H2 and H3 are small, pure functions with
  existing tests. H4 is documentation. The risk is bounded, and each item can
  be reverted on its own.

### D3. Do not carry the virtual microphone forward inside either repository

- **Driver:** criteria 3 and 4. It needs root, code signing, and sandbox IPC
  work; it currently has defects that make it silent or choppy; and mature
  alternatives exist.
- **What would change my mind:** if a system-wide "only my voice" mic for
  meeting apps is a first-class goal for you, it deserves its own repository.
  Start from `mvx_ring.h` and `ring.py` (which are sound), fix the segment
  lifecycle (create once, never unlink while the driver may be mapped, put a
  generation counter in the header), fix the permissions (a world-readable
  segment, or a Mach-service IPC declared in the plug-in's Info.plist), gate on
  512-sample windows, and drain enhancer buffers in strict order.

### D4. Fix voicemode's interface on the server, not with client hooks

- **Driver:** the evidence is your own setup. A global rule and a Rust hook
  both exist to stop agents passing knobs the server advertises. Hooks only
  protect the clients you've wired, and a hook that exits 0 on failure protects
  nothing.
- **Defense:** shrinking the schema saves about 4k tokens per session for every
  host and removes a whole class of misuse. Keeping the old parameters as
  accepted-but-ignored keeps existing callers working.

### D5. Full duplex and voice barge-in go through LiveKit/WebRTC; local stays half duplex

- **Driver:** physics plus criterion 4.
  - Voice barge-in with open speakers requires acoustic echo cancellation,
    otherwise the assistant's own TTS triggers the VAD.
  - mvx got echo cancellation from the browser's WebRTC stack. voicemode's
    local path uses PortAudio with no echo cancellation.
  - voicemode already ships a loopback-only LiveKit server, a browser room, and
    an agent session with Silero VAD.
- **Defense:** this reuses maintained echo cancellation, jitter buffering, and
  turn handling instead of rebuilding them. The local transport keeps its
  strengths (no browser, control-channel barge-in, media keys). H3's
  heard/unheard split works on both.
- **What would change my mind:** a measured local echo-cancellation option (for
  example macOS voice-processing I/O) that keeps self-trigger rates near zero
  on laptop speakers. Then local voice barge-in becomes viable.

### D6. Replace mvx-style "readiness" with one real benchmark

- **Driver:** criterion 2. A verdict computed from constants cannot change
  anyone's decision. A replay benchmark produces numbers that gate H1 and H2
  and catch regressions.

### D7. Fork hygiene comes first

- **Driver:** legal and reputational exposure (the missing LICENSE, author
  misattribution, a redistributed copyrighted PDF), plus a release path that
  depends on a now-broken resolver. These have to be fixed before anything
  ships.

---

## 8. Suggested sequence

1. **R0 + R1** (licensing, attribution, green suite, release path). Gate: full
   suite green, `scripts/release.py --current` works, and LICENSE present.
2. **R4** benchmark harness. Gate: baseline JSONL for the current batch listen
   path on your machine.
3. **R2** schema shrink, with back-compat. Gate: the existing converse tests
   pass, the schema is under 3k characters, and the hook's parameter rewriting
   becomes a no-op.
4. **H2 + H3** (semantic hold, heard/unheard split). Gate: replay shows fewer
   cutoffs, and tests cover the stop and skip-forward split.
5. **H1** streaming listen backend, default off. Gate: the R4 numbers meet the
   H1 threshold.
6. **R3** module split once behavior is pinned by the steps above, then **R5**
   LiveKit hardening toward D5.
7. **Housekeeping, your call:**
   - Mark mvx-connect "superseded" in its README rather than deleting it; it
     still documents useful experiments.
   - If both stacks are installed, unload `com.mvx.connect.*` so its watchdog
     stops restarting voicemode's services. A second MLX server on 42007 also
     loads Kokoro twice.

---

## 9. Risks and open questions

- **mlx-audio version tension.** H1 assumes `/v1/realtime` exists in the
  pinned 0.4.3. The local checkout's `v0.4.3` tag has it, but a second `0.4.3`
  tag without the `v` does not. Confirm against the installed PyPI wheel. If it
  is missing, the upgrade path collides with the Kokoro decoder crash that
  motivated `<0.4.4`. Mitigation: run STT realtime and Kokoro TTS on separate
  mlx-audio instances, or wait for a fixed upstream release.
- **Voxtral model availability.** mvx used a locally converted
  `Voxtral-Mini-4B-Realtime-2602-4bit` under `~/.omlx/models`. Licensing and
  distribution for voicemode users need checking before making it a default.
- **Unverified items.** Section 4 item 3's shared-memory permission failure
  (on hardware) and native LiveKit playback (R5) both need confirmation. The
  first only matters if D3 changes.
- **Your direction may differ from my inference.** If your priority is the
  "agent-delegated presentation" mode in mvx's VISION note, the recommendation
  gets stronger, not weaker: build it on voicemode `turns[]` plus conch plus
  `converse_continue`, and add a progress/status read-back (turn index, heard
  text) using H3.

---

## Appendix A: defect index with locations

### mvx-connect

- `src/mvx_connect/gateway/app.py`: the realtime path has no spool or JSONL
  writes; the guardian auto-whisper holds the shared MLX lock; `finalize_turn`
  is fine.
- `src/mvx_connect/gateway/client/app.js`: `markAssistantSpeaking` uses fixed
  text with `totalAudioMs: 4200`; the logo text is "QA".
- `src/mvx_connect/guardian/local_llm.py`: a separate `mlx-guardian` thread
  holds `MLX_REALTIME_LOCK` during generation.
- `src/mvx_connect/gateway/speech_gate.py`: Silero needs 512 samples; smaller
  inputs return `False`.
- `src/mvx_connect/driver/writer.py`: 10 ms blocks feed that gate, and the
  enhancer warm-up passes raw audio through.
- `src/mvx_connect/driver/ring.py` and `native/mvx-driver/src/MVXVoice.c`:
  unlink and recreate on writer restart versus map-once-while-NULL in the
  driver; segment mode `0600`.
- `src/mvx_connect/gateway/mlx_cli_transcriber.py`: Qwen3 is forced to
  `--language en`, and every call is a fresh subprocess.
- `src/mvx_connect/cli.py`: `mvx mcp` re-parses `sys.argv`.
- `bench/denoise_rtf.py`: imports `mlx_voice_agent`.
- `bin/mvx-watchdog`: defaults to voicemode launchd labels, and its live-session
  detection is blind to the realtime path.
- `pyproject.toml`: missing `deepfilternet`, `torch`, `torchaudio`,
  `speechbrain`, and `mlx-audio` for the defaults the installer selects.
- Docs: test and tool counts disagree, the connect/chat semantics are inverted
  versus the branding, and `runtime/mcp_probe.py` doesn't exist.

### voicemode

- `LICENSE`: deleted in `62b4947`.
- `d824a83`: the global `mbailey` → `IB-QA` replace.
  `tests/test_provider_selection.py:366` is a `SyntaxError`; there are
  misattributed quotes in `tools/converse.py`, `control_channel.py`, and tests;
  and `tests/test_release_remote_resolution.py` has 3 failures.
- `tests/test_converse_pre_tool_use_hook.py`: 9 failures; the target script was
  removed.
- `tests/test_concurrent_stdio.py::test_sounddevice_stderr_redirect_disabled`:
  1 failure, root cause not investigated.
- `.claude/settings.json`: references deleted scripts. `.cursor/hooks.json`
  uses an absolute user path.
- `voice_mode/tools/converse.py`: 31-parameter schema at about 16.6k
  characters, behavioral instructions in the docstring, the docstring
  duplicated in `_converse_core`, and the uncommitted `loop._default_executor`
  use.
- `voice_mode/reconnect.py`: tmux TUI scraping.
- `voice_mode/livekit/transport.py`: a session per call. `native.py`: remote
  playback unverified.
- Repo root: `2509.00078v2.pdf` (IEEE notice); `voice_mode/data/hooks/bin/voicemode_hook`
  is a 2.4 MB binary; the README and `pyproject.toml` URLs are malformed.
