---
description: Keep waiting on an in-progress VoiceMode converse job. Do not start a new recording.
---

# /voicemode:converse_continue

When `converse` returns `status: in_progress`, call `converse_continue` with that `job_id`. The original speech, microphone, and transcription keep running inside the server.

## Implementation

Pass only:

- `job_id` — exact ID from the in-progress converse result
- `wait_seconds` — optional; default 50, capped at 55

Do not start a new `converse` recording while that job is active. Repeat `converse_continue` until you get a spoken reply or a final error.

```bash
# After converse returns job_id=…
# converse_continue job_id=<id> wait_seconds=50
```
