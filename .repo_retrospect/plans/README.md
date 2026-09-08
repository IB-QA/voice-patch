# VoiceMode Plan Archive

This folder keeps the relevant planning artifacts inside the workspace so they
survive repository replacement and conversation compaction.

## Plans

- `timeout-safe-converse-jobs-original.md` — the earlier async-job proposal,
  preserved as historical context. It is not approved for implementation.
- `voicemode-reliability-observation-plan.md` — the current observation-first,
  collaborative plan. This is the active plan.

## Related context

- `../voicemode-report-changes/` — prior implementation bundle.
- `../../.cursor/artifacts/usage-observatory/HANDOFF.md` — usage-observatory
  handoff and evidence contract.

## Operating rule

Stock PyPI VoiceMode 8.12.0 remains the observation baseline. Before any
development build is installed, it must have a distinct development identity
and a separate executable/MCP entry. Installation and service commands are run
collaboratively, with expected and actual effects recorded before continuing.
