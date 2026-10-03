# VoiceMode

**Private working clone derived from [IB-QA/voicemode](https://github.com/IB-QA/voice-patchvoicemode).**

> Natural voice conversations with MCP-capable coding agents

VoiceMode is a local MCP server for speech-to-text and text-to-speech. Voice isn't about replacing typing - it's about being available when typing isn't.

**Perfect for:**

- Walking to your next meeting
- Cooking while debugging
- Giving your eyes a break after hours of screen time
- Holding a coffee (or a dog)
- Any moment when your hands or eyes are busy

## See It In Action

[![VoiceMode Demo](https://img.youtube.com/vi/cYdwOD_-dQc/maxresdefault.jpg)](https://www.youtube.com/watch?v=cYdwOD_-dQc)

## Quick Start

**Requirements:** Computer with microphone and speakers

### Option 1: Plugin installer (recommended)

Wires VoiceMode at user level for Cursor, Claude Code, Copilot, Codex, and the other supported clients:

```bash
uv sync
uv run voicemode plugin install --client=all
```

Then start talking with the `converse` MCP tool, or:

```bash
uv run voicemode converse "Hello"
```

### Option 2: Python installer package

Installs dependencies and the VoiceMode Python package.

```bash
# Install UV package manager (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run the installer (sets up dependencies and local voice services)
uvx voice-mode-install

# Wire the MCP server into your client(s)
uv run voicemode plugin install --client=all

# Optional: Add OpenAI API key as fallback for local services
export OPENAI_API_KEY=your-openai-key

# Start a conversation
uv run voicemode converse "Hello"
```

For manual setup, see the [Getting Started Guide](docs/tutorials/getting-started.md).

## Features

- **Natural conversations** - speak naturally, hear responses immediately
- **Works offline** - optional local voice services (Whisper STT, Kokoro TTS)
- **Low latency** - fast enough to feel like a real conversation
- **Smart silence detection** - stops recording when you stop speaking
- **Privacy options** - run entirely locally or use cloud services
- **Self-hosted browser rooms** - optional loopback LiveKit SFU and browser
  microphone transport, restored in this private fork

## Compatibility

**Platforms:** Linux, macOS, Windows (native or WSL), NixOS
**Python:** 3.10-3.14

## Configuration

VoiceMode works out of the box. For customization:

```bash
# Set OpenAI API key (if using cloud services)
export OPENAI_API_KEY="your-key"

# Or configure via file
voicemode config edit
```

See the [Configuration Guide](docs/guides/configuration.md) for all options.

## Permissions Setup (Optional)

To use VoiceMode without permission prompts, add to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse",
      "mcp__voicemode__service"
    ]
  }
}
```

See the [Permissions Guide](docs/guides/permissions.md) for more options.

## Local Voice Services

For privacy or offline use, install local speech services:

- **[Whisper.cpp](docs/guides/whisper-setup.md)** - Local speech-to-text
- **[Kokoro](docs/guides/kokoro-setup.md)** - Local text-to-speech with multiple voices
- **[LiveKit browser rooms](docs/guides/livekit-setup.md)** - Self-hosted,
  loopback browser microphone rooms with explicit LiveKit transport

Whisper and Kokoro expose OpenAI-compatible APIs, so VoiceMode can switch
between local and cloud speech providers.

## Installation Details

<details>
<summary><strong>System Dependencies by Platform</strong></summary>

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y ffmpeg gcc libasound2-dev libasound2-plugins libportaudio2 portaudio19-dev pulseaudio pulseaudio-utils python3-dev
```

**WSL2 users**: The pulseaudio packages above are required for microphone access.

#### Fedora/RHEL

```bash
sudo dnf install alsa-lib-devel ffmpeg gcc portaudio portaudio-devel python3-devel
```

#### macOS

```bash
brew install ffmpeg node portaudio
```

#### NixOS

```bash
# Use development shell
nix develop github:IB-QA/voicemode

# Or install system-wide
nix profile install github:IB-QA/voicemode
```

<details>
  <summary>
    <strong>Alternative Installation Methods</strong>
  </summary>
</details>

#### From source

```bash
git clone https://github.com/IB-QA/voice-patchvoicemode.git
cd voicemode
uv tool install -e .
```

#### NixOS system-wide

```nix
# In /etc/nixos/configuration.nix
environment.systemPackages = [
  (builtins.getFlake "github:IB-QA/voicemode").packages.${pkgs.system}.default
];
```

</details>

## Troubleshooting

| Problem | Solution |
| --------- | ---------- |
| No microphone access | Check terminal/app permissions. WSL2 needs pulseaudio packages. |
| UV not found | Run `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| OpenAI API error | Verify `OPENAI_API_KEY` is set correctly |
| No audio output | Check system audio settings and available devices |

### Save Audio for Debugging

```bash
export VOICEMODE_SAVE_AUDIO=true
# Files saved to ~/.voicemode/audio/YYYY/MM/
```

## Documentation

- [Getting Started](docs/tutorials/getting-started.md) - Full setup guide
- [Configuration](docs/guides/configuration.md) - All environment variables
- [Whisper Setup](docs/guides/whisper-setup.md) - Local speech-to-text
- [Kokoro Setup](docs/guides/kokoro-setup.md) - Local text-to-speech
- [LiveKit Browser Rooms](docs/guides/livekit-setup.md) - Optional self-hosted room transport
- [Development Setup](docs/tutorials/development-setup.md) - Contributing guide

Full documentation: [voicemode.dev](https://voicemode.dev)

## Links

- **Website**: [voicemode.dev](https://voicemode.dev)
- **GitHub**: [github.com/IB-QA/voicemode](https://github.com/IB-QA/voice-patchvoicemode)
- **PyPI**: [pypi.org/project/voice-mode](https://pypi.org/project/voice-mode/)
- **YouTube**: [@getvoicemode](https://youtube.com/@getvoicemode)
- **Twitter/X**: [@getvoicemode](https://twitter.com/getvoicemode)
- **Newsletter**: [![Subscribe](https://img.shields.io/badge/Subscribe-Newsletter-orange?style=flat-square)](https://buttondown.com/voicemode)

## License

MIT - A [Failmode](https://failmode.com) Project

---
mcp-name: dev.voicemode/voicemode
