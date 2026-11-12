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

**Never end your turn while a job is in progress.** The user is still on the call. Each in-progress reply has an `instruction`, a rising `poll`, and `elapsed_seconds`; many polls in a row are normal. Do not write a summary, and do not stop and report.

```bash
# After converse returns job_id=…
# converse_continue job_id=<id> wait_seconds=50
```
