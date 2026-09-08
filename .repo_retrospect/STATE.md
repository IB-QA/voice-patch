# Session state — resume here after Cursor reload

## Done

- **Compared the three MCP tools.** Codebase Memory MCP is the right codebase-memory
  layer (11 repos already indexed). Graphit Live is JS/TS-only in practice — its
  Python parser fails with "Extension path required for WASM parser
  initialization", and `analyze_file_logic` on `voice_mode/server.py` returned an
  empty graph. Memgraph is a plain graph DB and its server is **down**
  (`bolt://localhost:7687` refuses connections).
- **Diagnosed VoiceMode Bridge.** See `FINDINGS.md`. Root cause: Cursor never
  loaded the plugin's `hooks/hooks.json`; only the global `~/.cursor/hooks.json`
  runs. The voicebridge adapter code itself is correct (verified by hand).
- **Deployed the fix.** `~/.cursor/hooks.json` now includes the four voicebridge
  hooks alongside the session-replay collector.
  Backup: `~/.cursor/hooks.json.bak-20260906-124154`.
  Reloaded and verified at 12:48:08: `beforeShellExecution` created current
  session state with `{"active": true}`.
- **Fixed the VoiceBridge handoff race.** `stop` could run before the blocking
  `afterAgentResponse` hook finished listening, return `{}`, and leave the
  transcript stranded in `pending_reply`. It now waits for the matching
  `generation_id`; the stop-hook timeout is 360 seconds. A delayed-reply
  rendezvous test passed.
- **Audited session-replay.** The JSONL event ledger is complete and reliable
  (125 events captured this session). The `summary.json` writer is buggy.
- **Reviewed `eventCapture`.** It covers substantially more Cursor hook events
  than session-replay and is the better ingestion starting point, but it needs
  transactional storage, schema/version IDs, idempotency, safe redaction, and
  cross-tool normalization.
- **Reviewed and indexed `usage-observatory`.** All 9 tests pass. Codebase
  Memory indexed 224 nodes and 902 edges with no skipped or partial source
  parses. Its current implementation is a strong aggregate analytics prototype,
  not yet a durable memory/reconciliation system.
- **Persisted the observatory ADR in Codebase Memory.** It records SQLite WAL as
  the application-owned source of truth, an optional rebuildable graph,
  canonical source adapters, OTEL/billing reconciliation, and evidence-linked
  exports and insights.

## Open bug — session-replay summary writer

`collector.py` lines 380-383 use a **fixed** temp filename:

```python
tmp = summary_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(summary, fh, default=str, indent=2)
os.replace(tmp, summary_path)
```

Cursor fires several hooks concurrently, so multiple collector processes race on
that one path. One wins `os.replace`, the others hit
`FileNotFoundError: ... summary.json.tmp -> ... summary.json`. **825 failures**
logged in `data/_collector-errors.log`.

Consequences: summary updates are silently dropped, `turns` is stuck at `0`, and
per-turn cost stays `0.0`. A unique temp name fixes the `FileNotFoundError`, but
not concurrent lost updates. The durable fix is a transactional single-writer
store (SQLite WAL), with summaries derived from committed events.

## Task queue (user's stated order)

1. ~~Fix + deploy the voicebridge hook~~
2. ~~Verify activation through the bridge~~
3. Revisit the MCP tooling question (Codebase Memory indexing of this repo)
4. Work on the VoiceMode repository itself
5. Build the global usage/memory observatory after its reference repository is
   copied into `_inspect/`

## Dashboard requirements (from the user)

- Local UI, eventually covering *all* tools they use, **starting with Cursor**
- Aggregate/global view, not just per-session replay: total cost, total token
  consumption, agent counts, tool-call counts, overall statistics
- Export a session to **HTML, PDF, or JSON**
- They have an existing "usage observatory" UI to model it on — **path not yet
  provided**, they were still searching. Ask again.
- They copied `_inspect/eventCapture/` (cursor-hook-router, `router.py`,
  `policy.py`, `transcript.py`, `session_registry.json`) as additional prior art
  — reviewed; reuse its broad hook routing, not its NDJSON-only persistence.

## Provisional observatory architecture

- **System of record:** SQLite in WAL mode, storing immutable raw events,
  normalized entities, exact/estimated usage facts, historical price rates,
  provenance, exports, and versioned insights.
- **Ingestion:** thin host adapters send canonical versioned envelopes to one
  local daemon over a Unix socket; failures spool to unique files and fail open.
- **Search:** SQLite FTS plus local embeddings for semantic retrieval.
- **Graph:** a rebuildable projection for sessions, turns, messages, agent runs,
  tools, files, edits, decisions, outcomes, and evidence. Neo4j Community is the
  current recommendation; FalkorDB is the runner-up. Do not place raw payloads
  in the graph.
- **API/UI:** localhost-only service for global analytics, replay, graph/semantic
  search, naming/tagging, provenance, and export.
- **Exports:** one canonical export model rendered as JSON, Markdown,
  self-contained HTML, or PDF, in full-evidence and curated-context modes.
- **Insights:** immutable, versioned evaluator results linked to exact evidence;
  never overwrite captured events or earlier assessments.

### Usage Observatory reuse decision

- Reuse its dashboard and chart rendering, loopback server protections,
  provider capability registry, platform discovery, work-item contracts,
  deterministic advisor rules, and privacy regression tests.
- Adapt `SnapshotBuilder`, provider adapters, models, UI, advisor findings, and
  work-item mappings to query/write normalized SQLite records.
- Replace bounded JSONL/JSON as authoritative storage, request-time source
  scanning, heuristic OTEL import, side-effecting provider sync over `GET`, and
  Copilot-specific credit-to-dollar assumptions.
- Minimal vertical slice: Cursor hook → local daemon → SQLite WAL → aggregate
  dashboard → chronological session replay/naming → JSON/Markdown/HTML/PDF
  export → FTS5 search.
- Important repository warning: the copied observatory checkout has only one
  initial commit; nearly the entire implementation is currently untracked.
  Preserve or commit it before doing substantive development.

### Important security defect in `eventCapture`

`router.py::_append_transcript` reads the original unredacted event rather than
the redacted record. `env_filtered` also bypasses `_envelope`, so credentials
may escape redaction. Do not deploy it globally until these paths are fixed.

### Exact billing requirement

Cursor hooks are observational and do not expose authoritative token meters.
For Enterprise, Cursor's OTEL `cursor.api.request` logs provide per-request
input, output, cache-read and cache-creation tokens and join keys:
`cursor.conversation.id`, `cursor.request.id`, and `cursor.usage_event.id`.
`cursor.api.correction` can retroactively mark a usage event not billed. Logs
are at-least-once and must be deduplicated by `cursor.event.id`; metrics are
delta, at-most-once, and lack session IDs.

Cursor's OTEL cost metric remains explicitly best-effort rather than an invoice.
Exact money must reconcile usage-event IDs against Cursor Admin/billing exports
and invoices. For third-party models, current Teams pricing is public list API
price plus the $0.25/M Cursor Token Rate applied to input, output, and cached
tokens. Cursor first-party models (Composer and Cursor Grok) are exempt. Price
history must be effective-dated; refreshing prices alone cannot reconstruct
missing usage quantities.

### Decisions still needed

1. Is Cursor Enterprise OTEL available for this team, and can an HTTPS OTLP
   receiver be exposed? Cursor's export is server-side and requires a publicly
   reachable authenticated endpoint.
2. Which Cursor Admin/billing API access and invoice exports are available for
   authoritative cost reconciliation?
3. May a local Docker service run continuously, or must phase one be embedded?
4. Capture full thoughts/tool payloads/file contents, or redacted excerpts by
   default?
5. Must embeddings and evaluators be local-only?
6. Required retention period and whether database/blob encryption is mandatory.
7. Path to the existing usage-observatory repository.

## Known blocker, unresolved

`index_repository` on `/Users/ibhatt/Downloads/voicemode` fails in both `full`
and `fast` mode with a generic "Pipeline failed" error. The repo has 126 Python
files under `voice_mode/`, so it is not an empty-source problem. Needs debugging.

## Voice settings that work

The bridge is active and uses the `voicemode` CLI through a hook with a
360-second timeout. The MCP `converse` fallback still needs
`listen_duration_max: 55` and `timeout: 55`.
