#!/bin/sh
# Build voicemode_hook into the VoiceMode cache (not into an IDE folder).
# Usage: build.sh [DEST_PATH]
# Default: ~/.voicemode/services/hooks/voicemode_hook
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/.voicemode/services/hooks/voicemode_hook}"
if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo is required to build voicemode_hook" >&2
  exit 1
fi
cargo build --release --manifest-path "$ROOT/Cargo.toml"
mkdir -p "$(dirname "$DEST")"
cp "$ROOT/target/release/voicemode_hook" "$DEST"
chmod +x "$DEST"
echo "$DEST"
