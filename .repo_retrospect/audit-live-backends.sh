#!/usr/bin/env zsh
# READ-ONLY post-install audit. Does not start, stop, install, or remove anything.

OUT="${0:A:h}/observations/live-backends-$(date +%Y-%m-%d-%H%M%S).txt"
mkdir -p "${OUT:h}"

s() { print -r -- "\n===== $* =====" >>"$OUT"; }
r() {
  print -r -- "\$ $*" >>"$OUT"
  eval "$@" >>"$OUT" 2>&1
  print -r -- "[exit $?]" >>"$OUT"
}

print -r -- "VoiceMode live backend audit — $(date)" >"$OUT"

s CONFIG
r "grep -E 'VOICEMODE_(TTS_BASE_URLS|STT_BASE_URLS|WHISPER_MODEL|WHISPER_PORT|KOKORO_PORT|MLX_AUDIO_(PORT|HOST|BASE_URL)|IMPRESSIONS_MODEL)' ~/.voicemode/voicemode.env"

s CLI_CONTRACT
r "voicemode service install --help"
r "voicemode service uninstall --help"
r "voicemode whisper model"
r "voicemode whisper model --all"

s SERVICES
r "voicemode status"
r "voicemode service status whisper"
r "voicemode service status kokoro"
r "voicemode service status mlx-audio"
r "launchctl list | grep -i voicemode || echo '(no voicemode jobs)'"

s PORTS
for port in 2022 2060 8880 8090 8890 8765 8785; do
  r "lsof -nP -iTCP:$port -sTCP:LISTEN || echo '($port free)'"
done

s WHISPER
r "find ~/.voicemode/services/whisper/models -maxdepth 1 -type f -print 2>/dev/null | sort"
r "grep -n -E 'MODEL_NAME|MODEL_PATH|WHISPER_PORT|--port|--model|FALLBACK' ~/.voicemode/services/whisper/bin/start-whisper-server.sh"
r "tail -80 ~/.voicemode/logs/whisper/whisper.out.log"
r "tail -80 ~/.voicemode/logs/whisper/whisper.err.log"

s KOKORO
r "tail -5 ~/.voicemode/services/kokoro/start-gpu_mac.sh"
r "tail -60 ~/.voicemode/logs/kokoro/kokoro.out.log"
r "tail -60 ~/.voicemode/logs/kokoro/kokoro.err.log"

s MLX_AUDIO
r "uv tool list | grep -A3 -B1 'mlx-audio' || true"
r "ls -l ~/.local/bin/mlx_audio.server"
r "plutil -p ~/Library/LaunchAgents/com.voicemode.mlx-audio.plist"
r "curl -fsS http://127.0.0.1:8890/ || echo '(mlx root unavailable)'"
r "curl -fsS http://127.0.0.1:8890/v1/models || echo '(mlx models unavailable)'"
r "curl -fsS http://127.0.0.1:8890/openapi.json > /tmp/voicemode-mlx-openapi.json && python3 -c 'import json; d=json.load(open(\"/tmp/voicemode-mlx-openapi.json\")); print(\"\\n\".join(sorted(d.get(\"paths\", {}))))' || echo '(mlx OpenAPI unavailable)'"
r "find ~/.cache/huggingface/hub -maxdepth 1 -type d -name 'models--mlx-community--*' -print 2>/dev/null | sort"
r "du -sh ~/.local/share/uv/tools/mlx-audio ~/.cache/huggingface/hub/models--mlx-community--* 2>/dev/null"
r "tail -120 ~/.voicemode/logs/mlx-audio/mlx-audio.out.log"
r "tail -160 ~/.voicemode/logs/mlx-audio/mlx-audio.err.log"

print -r -- "\naudit written to: $OUT"
print -r -- "lines: $(wc -l <"$OUT")"
