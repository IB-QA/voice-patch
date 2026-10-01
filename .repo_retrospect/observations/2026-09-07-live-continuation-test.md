# Live long-turn test — 8.12.8-ib-dev on IB-QA/voice-patch

Date: 2026-09-07
Build under test: `8.12.8-ib-dev.a670579` (repo-local `.venv`, editable install)
Host: Cursor, MCP over stdio
Services: local STT (`STT: local`), local TTS

## Why there is no stock baseline

The intent was to compare stock 8.12.0 against the patched build. That
comparison was not possible: Cursor's MCP entry was bare `uv run voicemode`
with no `--directory`, and it resolved to this project, so the running server
already carried the continuation work. Confirmed by the live tool schema
exposing both `continuation_wait` and the `converse_continue` tool, neither of
which exists in stock 8.12.0.

The MCP entry is now pinned:

```json
{ "command": "uv", "args": ["--directory", "/Users/ibhatt/Downloads/voicemode", "run", "voicemode"] }
```

## Run 1 — 58s cap, oversized prompt (non-continuation path)

`listen_duration_max=58`, below the 60s auto-continuation threshold.

| phase | value |
| --- | --- |
| ttfa | 2.4s |
| gen | 2.4s |
| play | 57.4s |
| record | 13.8s |
| stt | 0.0s |
| **total** | **73.6s** |

Result: `No speech detected`. The prompt itself was too long, so TTS consumed
the window and the user never spoke; recording self-terminated at 13.8s.

Notable anyway: **the request completed at 73.6s without the host killing it**,
with continuation *not* engaged. So Cursor's practical MCP deadline is above
73s, not the ~60s previously assumed.

## Run 2 — 58s cap, short prompt (non-continuation path)

| phase | value |
| --- | --- |
| ttfa | 1.1s |
| gen | 1.1s |
| play | 6.1s |
| record | 39.3s |
| stt | 0.5s |
| audio | 1223KB |
| **total** | **47.0s** |

Full transcript returned. Recording ended by silence detection at 39.3s, well
inside the 58s cap, so the cap was never the binding constraint.

## Run 3 — 90s cap (continuation path) — the result that matters

`listen_duration_max=90`, above the threshold. Continuation engaged.

The first `converse` call returned a job rather than a result:

```json
{"status":"in_progress","job_id":"9c7a3b148b2140828057c60f51b9d217",
 "message":"Voice operation is still active; do not start a new recording.",
 "next":{"tool":"converse_continue","arguments":{"job_id":"...","wait_seconds":50.0}}}
```

Two `converse_continue` calls followed. The first returned `in_progress` again;
the second returned the completed result.

| phase | value |
| --- | --- |
| ttfa | 1.2s |
| gen | 1.2s |
| play | 72.3s |
| record | 45.0s |
| stt | 0.6s |
| audio | 1400KB |
| **total** | **119.1s** |

**A single voice turn spanned 119.1 seconds across three MCP requests and
returned its transcript complete and untruncated.** The microphone was never
restarted, no partial transcript entered context, and nothing was cut mid-word.
This is the behaviour the change set exists to produce, confirmed end to end
against a real host.

## Test suite

`1926 passed, 58 skipped` under an isolated `VOICEMODE_BASE_DIR` with audio
feedback, chimes, and the cancel announcement disabled.

Six failures appeared on the first run, all in
`tests/test_release_remote_resolution.py`, and all caused by the rebrand rather
than the continuation work: `scripts/release.py` stores the canonical slug as a
tuple, `("IB-QA", "voicemode")`, which the literal string replace of
`IB-QA/voicemode` could not reach. It had become `("IB-QA", "voicemode")` —
owner rewritten, repo name not — so `resolve_github_remote()` returned `None`
for every real remote. Fixed in `a670579`.

## Still open

- Run 1's `No speech detected` is not a defect, but a genuine 58s *spoken*
  turn on the non-continuation path has not been measured. Worth one more run
  with a short prompt and sustained speech to find where the host actually
  cuts.
- Issue #532 (mic hard-cut at `listen_duration_max` while speech is in
  progress) remains unaddressed here. Silence detection ended both real
  recordings early, so the cap was never reached and the bug was never
  exercised.
