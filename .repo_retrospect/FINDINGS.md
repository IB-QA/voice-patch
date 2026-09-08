# VoiceMode Bridge — why it isn't working

## Short version

The voicebridge code is fine. Cursor is simply never calling it.
Your plugin's `hooks/hooks.json` is not being executed; only the global
`~/.cursor/hooks.json` is.

## Evidence

1. **Plugin hooks never ran.** Session state lives in
   `~/.local/state/voicebridge/sessions/`. The newest file there was written
   19 days ago. Running `voicebridge session activate` in this session wrote
   nothing new.

2. **Global hooks DO run.** The session-replay collector, wired in
   `~/.cursor/hooks.json`, wrote `data/<conversation_id>.jsonl` during this
   very session. So Cursor's hook system is alive — it just isn't loading the
   plugin's hook file.

3. **The plugin itself IS loaded.** Its rule
   (`rules/voicemode-bridge.mdc`) is applied to the agent. So rules and
   commands load from the plugin; hooks do not.

4. **The adapter logic is correct.** Invoked by hand it works:

   ```
   echo '{"conversation_id":"TESTSESSION","command":"voicebridge session activate"}' \
     | voicebridge adapter cursor before-shell
   ```

   → wrote `{"active": true, ...}` to the session state file. No bug in the code.

## Why this causes the 60-second failures

Two completely different paths exist for speaking:

| Path | Mechanism | Timeout ceiling |
|------|-----------|-----------------|
| MCP `converse` tool (what we use today) | Cursor MCP call | **~60 s, Cursor-imposed** |
| voicebridge hook | `afterAgentResponse` shells out to the `voicemode` CLI | **360 s**, set in `hooks.json` |

Because the bridge is dead, every voice turn goes through the MCP tool and
inherits Cursor's 60-second cap. That is why `listen_duration_max` must be held
at ~55 s — anything longer gets killed mid-listen.

If the bridge worked, it would bypass MCP entirely: the hook runs
`voicemode converse -m <text>` as a subprocess (see `process.py`), which has no
60-second ceiling.

## The `beforeShellExecution` detail

Activation is not done by the CLI. Running `voicebridge session activate`
directly is almost a no-op — without `--host` and `--session-id` it only prints
`voice session activate requested` (see `cli.py`, the `session` branch).

The real activation happens when Cursor fires `beforeShellExecution`, whose
payload carries the `conversation_id`. The adapter matches the command string
exactly against `"voicebridge session activate"` and flips state to active.

**Your global hooks file has no `beforeShellExecution` entry at all.** So even
if the other hooks were wired, voice mode could never turn on.

## Proposed fix

`cursor-global/hooks.PROPOSED.json` — the existing global file with voicebridge
added alongside the collector. Nothing is removed; session replay keeps working.

Added:

- `beforeShellExecution` → `voicebridge adapter cursor before-shell` (the on/off switch)
- `afterAgentThought` → voicebridge entry appended (only speaks if `speakThoughts` is on; currently off)
- `afterAgentResponse` → voicebridge entry appended, 360 s timeout
- `stop` → voicebridge entry appended, `loop_limit: null` so the conversation can continue

To apply:

```bash
cp ~/.cursor/hooks.json ~/.cursor/hooks.json.bak
cp _inspect/cursor-global/hooks.PROPOSED.json ~/.cursor/hooks.json
```

Then reload the Cursor window. Cursor will prompt to trust the new hook commands.

## Caveats worth knowing before applying

- **Ordering is not guaranteed.** Both the collector and voicebridge will run on
  `afterAgentResponse`. The collector fails open and is fast, so this should be
  safe, but they are independent processes.
- **The bridge speaks every assistant response** once active. That is the design
  — it is not selective.
- **`voicebridge` resolves to an editable install** at
  `~/.claude/projects/-Users-ibhatt-claude-cursor-github-factory-pipeline/src/voicebridge`.
  If that directory moves or is deleted, the hooks break. Worth making this a
  real install.
- **No duration flag is passed.** `process.py` runs `voicemode converse -m <msg>`
  with no `-d`, so it uses VoiceMode's own default listen duration.
