---
name: Timeout-safe converse jobs
overview: Eliminate Cursor/Claude Desktop ~60s MCP tools/call timeouts for long converse sessions via lifespan-owned async jobs with adaptive cutover and a single long-poll tool — with honest host-specific autonomy claims after GPT-5.6 Sol review.
status: archived-unapproved
source: /Users/ibhatt/.cursor/plans/timeout-safe_converse_jobs_f0897555.plan.md
---

# Timeout-safe converse via async jobs (revised)

This is the earlier plan preserved for historical comparison. It must not be
implemented verbatim; the current plan requires a stock observation window and
a joint design decision first.

## Review outcome

Independent review by [Timeout plan review](f4b01244-94e9-4949-974f-58e0801174f0):
GO WITH CHANGES. Do not implement the first draft verbatim.

Agreed direction: async job plus polling. Mandatory revisions replaced the
original duration gate, split status/result tools, `state.json` job storage,
and mandatory Claude Code continuation claims.

## Problem statement

`converse` blocks TTS, listening, and STT. The earlier working assumption was
that Cursor and Claude Desktop abort `tools/call` around 60 seconds and that
progress notifications do not reset the deadline. Later research found no
current documented numerical Cursor IDE MCP timeout, so this assumption must be
measured rather than treated as a contract.

## Earlier chosen design

The earlier proposal used lifespan-owned asynchronous jobs with adaptive
cutover:

1. Start interactive execution as a managed job.
2. Await it with `asyncio.wait_for(asyncio.shield(job), budget)`.
3. Return the unchanged legacy string if it finishes under budget.
4. Otherwise return `{status: "running", job_id, phase, poll_after_ms, hint}`.
5. Let a later `converse_poll` call await the same task.
6. Cancel the job if the client explicitly cancels before cutover.

The suggested configuration was:

- `VOICEMODE_CLIENT_TOOL_BUDGET_S`, default 40–45 seconds.
- `VOICEMODE_CONVERSE_JOB_MODE=auto|always|never`.

## Earlier JobManager requirements

- Own jobs for the MCP process lifespan.
- Cancel local jobs on stdio EOF or shutdown and wait a bounded time for audio
  threads.
- Let HTTP jobs survive individual request completion.
- Mark persisted nonterminal jobs abandoned after restart.
- Persist metadata under `~/.voicemode/jobs/<id>.json` with atomic writes and
  restrictive permissions.
- Keep survey/UI `state.json` separate.
- Enforce one microphone owner per local audio channel.
- Track phases such as queued, acquiring conch, speaking, listening,
  transcribing, cancelling, completed, failed, cancelled, and abandoned.

## Earlier tool surface

- `converse`: legacy result for quick completion, otherwise a running handle.
- `converse_poll(job_id, wait_seconds)`: idempotent long-poll returning status
  or the final transcript.
- `converse_cancel(job_id)`: cooperative cancellation.

Continuation tools were required to load whenever `converse` was enabled in the
tool whitelist.

## Earlier conch and cancellation requirements

- Refresh conch ownership while a long job runs.
- Release conch only when execution reaches a terminal state.
- Keep cancellation cooperative because fixed-duration/VAD-disabled recording
  may not stop immediately.
- Never claim microphone shutdown until the recording thread actually exits.

## Earlier host-adapter assessment

- Cursor and Claude Desktop could preserve server work via early return and
  polling, but could not be claimed to autonomously issue the next tool call.
- Claude Code hooks might provide an advisory nudge or a hook-side waiter.
- MCP Tasks were deferred until host capability negotiation could be proven.

## Related tilde regression

Expand `VOICEMODE_EVENT_LOG_DIR` through the existing path-normalization helper
so a configured leading `~` does not create a literal workspace `~/` tree.

## Earlier verification scope

- Quick completion versus cutover.
- Idempotent poll and cooperative cancellation.
- Stdio transport-close cleanup.
- Tool-whitelist exposure.
- Conch heartbeat and contention.
- VAD-disabled cancellation.
- Hook behavior.
- Real Cursor and Claude Desktop black-box checks.

## Earlier success criteria

- Long turns return a continuation handle before the host deadline without
  restarting recording.
- Quick turns keep the legacy result.
- Shutdown leaves no orphaned microphone.
- Documentation makes only empirically supported host-autonomy claims.
- Event-log paths expand correctly.

## Superseded decisions

The following are explicitly deferred by the current plan:

- where the continuation clock starts;
- whether cutover is whole-call or phase-specific;
- the numerical cutover budget;
- survey/multi-turn continuation behavior;
- any assumption that Cursor IDE has a documented 60-second MCP timeout.
