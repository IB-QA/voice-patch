import {
  Participant,
  RemoteParticipant,
  RemoteTrack,
  RemoteTrackPublication,
  Room,
  RoomEvent,
  Track,
  TranscriptionSegment,
} from "livekit-client";

import "./styles.css";

type ScreenState =
  | "idle"
  | "authenticating"
  | "connected"
  | "reconnecting"
  | "microphone-denied"
  | "auth-error"
  | "room-error"
  | "disconnected";

interface Session {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
}

const app = document.querySelector<HTMLElement>("#app");
if (!app) {
  throw new Error("VoiceMode browser root is missing");
}

const fragment = new URLSearchParams(window.location.hash.slice(1));
let browserBearer = fragment.get("token") ?? "";
history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);

app.innerHTML = `
  <div class="shell">
    <header>
      <a class="wordmark" href="/" aria-label="VoiceMode home">VoiceMode</a>
      <p>Private browser room</p>
    </header>
    <section class="connection" aria-labelledby="connection-heading">
      <div class="state-line">
        <span class="state-dot" aria-hidden="true"></span>
        <div>
          <p class="eyebrow">Connection</p>
          <h1 id="connection-heading">Ready to connect</h1>
        </div>
      </div>
      <p id="connection-detail">Connect to create a private VoiceMode room.</p>
      <button id="connect" class="primary" type="button">Connect</button>
    </section>
    <section class="microphone" aria-labelledby="microphone-heading">
      <p class="eyebrow">Microphone</p>
      <h2 id="microphone-heading">Microphone is off</h2>
      <p id="microphone-detail">VoiceMode asks for access only after you choose to turn it on.</p>
      <button id="microphone" type="button" disabled>Turn on microphone</button>
    </section>
    <section class="activity" aria-labelledby="activity-heading">
      <div>
        <p class="eyebrow">Live status</p>
        <h2 id="activity-heading">Waiting for a room</h2>
      </div>
      <ol id="transcript" aria-live="polite" aria-label="Live transcript">
        <li class="empty">Agent transcript will appear here when available.</li>
      </ol>
    </section>
    <div id="remote-audio" hidden></div>
    <p id="announcer" class="sr-only" role="status" aria-live="polite"></p>
  </div>
`;

const connectButton = required<HTMLButtonElement>("#connect");
const microphoneButton = required<HTMLButtonElement>("#microphone");
const heading = required<HTMLElement>("#connection-heading");
const detail = required<HTMLElement>("#connection-detail");
const microphoneHeading = required<HTMLElement>("#microphone-heading");
const microphoneDetail = required<HTMLElement>("#microphone-detail");
const activityHeading = required<HTMLElement>("#activity-heading");
const transcript = required<HTMLOListElement>("#transcript");
const remoteAudio = required<HTMLElement>("#remote-audio");
const announcer = required<HTMLElement>("#announcer");
const shell = required<HTMLElement>(".shell");

let room: Room | null = null;
let screenState: ScreenState = "idle";

function required<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing required element: ${selector}`);
  return element;
}

function setState(state: ScreenState, message?: string): void {
  screenState = state;
  shell.dataset.state = state;
  const copy: Record<ScreenState, [string, string]> = {
    idle: ["Ready to connect", "Connect to create a private VoiceMode room."],
    authenticating: ["Creating your room", "Authenticating with the local VoiceMode gateway…"],
    connected: ["Connected", "Your private VoiceMode room is ready."],
    reconnecting: ["Reconnecting", "The room connection was interrupted. VoiceMode is retrying…"],
    "microphone-denied": ["Connected", "Room connected, but microphone access was denied."],
    "auth-error": ["Authentication failed", "Open this page again with “voicemode livekit browser open”."],
    "room-error": ["Room unavailable", "VoiceMode could not connect to the local LiveKit server."],
    disconnected: ["Disconnected", "The VoiceMode room has closed."],
  };
  [heading.textContent, detail.textContent] = message
    ? [copy[state][0], message]
    : copy[state];
  const active = state === "connected" || state === "microphone-denied";
  connectButton.textContent = active ? "Disconnect" : "Connect";
  connectButton.disabled = state === "authenticating" || state === "reconnecting";
  microphoneButton.disabled = !active;
  activityHeading.textContent = active ? "Listening for the agent" : "Waiting for a room";
  announcer.textContent = `${heading.textContent}. ${detail.textContent}`;
}

async function connect(): Promise<void> {
  if (room) {
    disconnect();
    return;
  }
  if (!browserBearer) {
    setState("auth-error");
    return;
  }
  setState("authenticating");
  try {
    const response = await fetch("/api/session", {
      method: "POST",
      headers: { Authorization: `Bearer ${browserBearer}` },
    });
    browserBearer = "";
    if (response.status === 401 || response.status === 403) {
      setState("auth-error");
      return;
    }
    if (!response.ok) {
      setState("room-error", `The local gateway returned ${response.status}.`);
      return;
    }
    const session = (await response.json()) as Session;
    const nextRoom = new Room();
    registerRoomEvents(nextRoom);
    await nextRoom.connect(session.serverUrl, session.participantToken, {
      autoSubscribe: true,
    });
    room = nextRoom;
    setState("connected");
  } catch {
    room = null;
    setState("room-error");
  }
}

function registerRoomEvents(nextRoom: Room): void {
  nextRoom
    .on(
      RoomEvent.TrackSubscribed,
      (
        track: RemoteTrack,
        _publication: RemoteTrackPublication,
        _participant: RemoteParticipant,
      ) => {
        if (track.kind === Track.Kind.Audio) {
          const element = track.attach();
          element.autoplay = true;
          remoteAudio.append(element);
        }
      },
    )
    .on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
      track.detach().forEach((element) => element.remove());
    })
    .on(RoomEvent.Reconnecting, () => setState("reconnecting"))
    .on(RoomEvent.Reconnected, () => setState("connected"))
    .on(RoomEvent.Disconnected, () => {
      room = null;
      remoteAudio.replaceChildren();
      setState("disconnected");
      resetMicrophone();
    })
    .on(
      RoomEvent.TranscriptionReceived,
      (segments: TranscriptionSegment[], participant?: Participant) => {
        for (const segment of segments) {
          if (!segment.final || !segment.text.trim()) continue;
          const empty = transcript.querySelector(".empty");
          empty?.remove();
          const item = document.createElement("li");
          const speaker = participant?.name || participant?.identity || "Agent";
          item.textContent = `${speaker}: ${segment.text}`;
          transcript.append(item);
        }
      },
    );
}

async function enableMicrophone(): Promise<void> {
  if (!room || screenState === "reconnecting") return;
  try {
    await room.localParticipant.setMicrophoneEnabled(true);
    microphoneHeading.textContent = "Microphone is on";
    microphoneDetail.textContent = "Your microphone audio is being shared with the agent.";
    microphoneButton.textContent = "Turn off microphone";
    microphoneButton.dataset.enabled = "true";
    setState("connected");
  } catch (error) {
    const denied =
      error instanceof DOMException &&
      (error.name === "NotAllowedError" || error.name === "PermissionDeniedError");
    setState(denied ? "microphone-denied" : "room-error");
    microphoneHeading.textContent = denied
      ? "Microphone permission denied"
      : "Microphone could not start";
    microphoneDetail.textContent = denied
      ? "Allow microphone access in browser settings, then try again."
      : "Check that a microphone is connected and available.";
  }
}

async function toggleMicrophone(): Promise<void> {
  if (!room) return;
  if (microphoneButton.dataset.enabled === "true") {
    await room.localParticipant.setMicrophoneEnabled(false);
    resetMicrophone();
    return;
  }
  await enableMicrophone();
}

function resetMicrophone(): void {
  microphoneHeading.textContent = "Microphone is off";
  microphoneDetail.textContent =
    "VoiceMode asks for access only after you choose to turn it on.";
  microphoneButton.textContent = "Turn on microphone";
  microphoneButton.dataset.enabled = "false";
}

function disconnect(): void {
  const activeRoom = room;
  room = null;
  activeRoom?.disconnect();
  remoteAudio.replaceChildren();
  resetMicrophone();
  setState("disconnected");
}

connectButton.addEventListener("click", () => void connect());
microphoneButton.addEventListener("click", () => void toggleMicrophone());
window.addEventListener("pagehide", disconnect);
setState("idle");
