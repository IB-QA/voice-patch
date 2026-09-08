# Resumable Audio Resilience

## Current behavior

- Cancellation during microphone recording propagates to the MCP request boundary.
- The recording worker is stopped, partial audio can be saved and transcribed, and
  VoiceMode plays the end chime plus `VoiceMode call cancelled.` by default.
- TTS and STT try configured endpoints in order when an endpoint fails before an
  operation completes.
- LiveKit sessions clean up their participant, room, and API client on cancellation.

These guarantees are covered by automated tests. They do not imply that an
interrupted utterance resumes from its last audible sample.

## Missing behavior

VoiceMode does not currently:

- reconnect the Cursor MCP client (client lifecycle is controlled by Cursor);
- assign a durable utterance ID with acknowledged playback progress;
- resume TTS playback at the last confirmed timestamp after process or transport loss;
- switch TTS providers in the middle of an already-started utterance;
- play the cancellation announcement for every TTS, provider, transport, or server
  failure;
- distinguish generated, delivered, buffered, and actually audible audio across
  process boundaries.

## Proposed contract

1. Persist each utterance before playback with an ID, text hash, format, sample rate,
   provider, and generated-audio location.
2. Checkpoint playback progress by sample offset. A checkpoint must represent audio
   handed to the output device, with its precision documented; it must not claim
   that buffered audio was audible.
3. Add an idempotent `resume_utterance(utterance_id)` operation that starts slightly
   before the checkpoint to avoid dropping words, with a bounded overlap window.
4. Keep generated PCM locally until completion or expiry so provider failure does not
   require regenerating already-produced audio.
5. If generation fails mid-stream, synthesize only the remaining text with the next
   configured provider, then continue playback with a short transition boundary.
6. Keep MCP reconnection client-owned. After Cursor reconnects, the server exposes
   interrupted utterances and permits explicit or policy-driven resume.
7. Use a separate, server-owned alert path for failure announcements so it cannot
   depend on the failed provider alone.

## Acceptance criteria

- Killing an MCP request during recording produces the cancellation chime and
  announcement and preserves configured artifacts.
- Interrupting playback at multiple checkpoints resumes with no missing words and
  no more than the configured overlap.
- Restarting the MCP server preserves resumable utterance metadata.
- Failure of the primary TTS before and during playback uses the configured fallback.
- Duplicate resume requests are idempotent and never start concurrent playback.
- Cancellation still propagates correctly and releases the conch and audio lock.
- Real tests cover Cursor-side cancellation/reconnection where the client supports it;
  unit tests alone are not accepted as proof of that path.
