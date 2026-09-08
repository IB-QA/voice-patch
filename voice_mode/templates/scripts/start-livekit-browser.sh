#!/usr/bin/env bash
set -euo pipefail

if [[ -f {ENV_FILE} ]]; then
    set -a
    source {ENV_FILE}
    set +a
fi

exec {PYTHON} -m voice_mode.livekit.browser_app
