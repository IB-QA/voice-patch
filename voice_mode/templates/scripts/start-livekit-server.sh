#!/usr/bin/env bash
set -euo pipefail

exec {LIVEKIT_BINARY} --config {LIVEKIT_CONFIG}
