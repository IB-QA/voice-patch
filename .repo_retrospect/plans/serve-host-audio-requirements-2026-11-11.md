# Handoff: VoiceMode serve, audio devices, and the larger system

Date: 2026-11-11
Status: requirements gathered. No code change. The next agent should not start from the picture page.

The person asked for this written down so another agent can pick it up. Scope is not approved. Do not implement from this file until they name the first build.

## What they asked to stop

A browser page of four picture-frames was put up and stepped through during speech. They rejected it. They called it a cartoon and said to leave it. Do not reopen that page, do not build another slide deck, and do not close their Safari tabs.

They also could not see a Cursor canvas. A path in chat was not a showcase. If a later visual is requested, it has to be a real browser page that changes while the explanation is spoken, and it has to be a technical walk, not labeled cards.

## What the code does today

`voicemode serve` (`voice_mode/cli.py`, `serve`, around lines 1971–2203) starts the same MCP server over HTTP so clients can connect without stdio. The command docstring says audio capture and playback happen on the host machine. Default endpoint shape: `http://<host>:<port>/mcp`.

That host audio is not a lookup of the connecting client. Local `converse` records with `sounddevice.sd.rec` and no device argument (`voice_mode/tools/converse.py`, `record_audio`, around lines 985–1020, and `listen_and_transcribe` around 1915–1939). Playback uses `sounddevice.OutputStream` with no device (`voice_mode/audio_player.py`, `NonBlockingAudioPlayer.play`). The mic and speakers are PortAudio's defaults for the process that is running the tool.

Two deployments follow from that:

| How the client connects | Where the process runs | Whose devices open |
| --- | --- | --- |
| IDE stdio, the usual install | The machine that launched the IDE | That machine |
| `voicemode serve` over HTTP | The machine where serve was started | That host, for every caller |

`voice_mode/mcp_launcher.py` only bridges to a remote server when `VOICEMODE_MCP_URL` is set. Otherwise it starts a local stdio server. A client that thinks it is "connecting to the MCP server" but is still on stdio never reaches the host process.

`converse` also has `transport="livekit"`. That path is separate from `sd.rec`. It was discussed as a later way to put a microphone on another machine while models stay on the Mac. It was not chosen.

Windows: CHANGELOG 8.11.0 says the MCP server, `converse`, and the CLI run natively on Windows 11. The person said a Windows install failed as incompatible. They later said the Windows machines do not have the hardware or the rights for the speech-model install. Both statements are in the record. Neither was reproduced in this session.

`converse.py` was read from source. Its graph index metadata had changed. The serve function and the audio player were read from source as well.

## Requirements, in the order they became clear

1. **Served audio must belong to the serving machine.** Connecting from another device must not open "my" sound devices just because the client is there. The serving process is what should own the devices. Only the VoiceMode server, the speech services, and the models are what that machine serves.

2. **Speech models stay on the Mac.** Whisper and Kokoro stay here. The Dell, the other Windows laptop, and the Windows servers should not get that install. Those machines do not have the capability, or the person does not have the rights.

3. **Talk and talk back from any machine.** An agent on any laptop or server must be able to speak to the person, and the person must be able to answer, using that machine's own devices or a chosen shared set. The session has to stay in sync. Location of the laptop must not make the agent mute.

4. **Platforms know each other and can hand work across machines.** Cursor, Claude Code, Claude Desktop, Claude Cowork, Codex, GitHub Copilot, and OpenBot show up across the Mac, the Dell, a second Windows laptop, Windows servers that already run agents and workflows, and an enterprise machine that is mostly Copilot. Each platform should see the tools and agents on the others and be able to call them. A task started on one machine should be continuable, or partly repeated, on another.

5. **One resident agent per machine, one dashboard, cheap work to OpenBot.** Each machine keeps one agent alive whose job is to report into a central dashboard so nothing is missed. Agents should consider remaining tokens and route work: do it, send it to deployed open-source models, or make it a workflow. OpenBot is a local group the person described as about ten bots that already coordinate and already track tokens. Trivial work goes there. Harder work stays with a stronger agent. Some product names in the spoken list were unclear (a second "open bot" / "rock bottom" / "charge BD") and should be confirmed, not guessed.

6. **Windows install does not match the docs.** The docs and changelog say native Windows works. The install the person tried did not. This was not reproduced here.

7. **Registration, not full replication.** When an MCP server or agent runtime is installed on a platform, it should register an id into a central store: live agents and profiles. Not every artifact should be copied onto every machine.

They also said the full cross-machine system might be too much to build immediately, then described it again as the actual goal. Treat "too big for right now" and "this is the system" as unresolved, not as a decision to build only the audio gate.

## What was proposed, and what it does not cover

The proposal spoken in this session was only:

- Keep Whisper and Kokoro on this Mac.
- Point other IDEs at `voicemode serve` over HTTP instead of local stdio.
- Refuse `converse` from a remote caller unless host audio is explicitly armed, so this Mac's mic does not open as a side effect.
- Leave local use at the Mac unchanged.
- Let OpenBot do the config-only steps. Keep the audio gate for a stronger agent.
- Defer a Dell microphone, LiveKit, the registry, and the dashboard.

Mapped to the requirements:

| Requirement | Covered by that proposal |
| --- | --- |
| 1. Serve-host devices, not the connecting client's | Only the negative half. A remote caller would stop opening the Mac mic. There is still no choice of device. |
| 2. Models stay on the Mac | Yes |
| 3. Talk and talk back from any machine | No. Deferred |
| 4. Cross-platform calls and cross-machine tasks | No |
| 5. Resident agent, dashboard, OpenBot routing | No, except two config tasks named for OpenBot |
| 6. Windows install failure | No. The proposal avoids the install. It does not fix it |
| 7. Register an id, do not replicate everything | No |

The person asked which of 3, 4, or 5 should be built first. They did not answer. They asked for this document instead.

## Do not assume

- Do not assume the audio gate is the approved first build.
- Do not assume LiveKit is the transport they want.
- Do not install Whisper or Kokoro on the Windows machines.
- Do not treat the changelog's Windows claim as confirmed. Reproduce the install failure.
- Product names that survived only as unclear speech need a confirmation pass.
