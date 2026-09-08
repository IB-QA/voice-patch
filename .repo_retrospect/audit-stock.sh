#!/usr/bin/env zsh
# READ-ONLY audit of the stock VoiceMode install.
# Starts nothing, stops nothing, installs nothing, deletes nothing.
#
# Run:   zsh _inspect/audit-stock.sh
# Output: _inspect/observations/audit-<timestamp>.txt   (path printed at the end)

setopt NO_ERR_EXIT 2>/dev/null
OUT="${0:A:h}/observations/audit-$(date +%Y-%m-%d-%H%M%S).txt"
mkdir -p "${OUT:h}"

s() { print -r -- "" >>"$OUT"; print -r -- "===== $* =====" >>"$OUT"; }
r() { print -r -- "\$ $*" >>"$OUT"; eval "$@" >>"$OUT" 2>&1; print -r -- "[exit $?]" >>"$OUT"; }

print -r -- "VoiceMode stock audit — $(date)" >"$OUT"

s IDENTITY
r 'which -a voicemode'
r 'voicemode --version'
r 'ls -l /Users/ibhatt/.local/bin/voicemode'
r 'echo $PATH | tr ":" "\n" | nl'

s PORTS
# 2022 whisper default, 2060 whisper as previously running,
# 8880 kokoro, 8890 mlx-audio, 8765 voicemode serve
r 'lsof -nP -iTCP:2022 -sTCP:LISTEN || echo "(2022 free)"'
r 'lsof -nP -iTCP:2060 -sTCP:LISTEN || echo "(2060 free)"'
r 'lsof -nP -iTCP:8880 -sTCP:LISTEN || echo "(8880 free)"'
r 'lsof -nP -iTCP:8890 -sTCP:LISTEN || echo "(8890 free)"'
r 'lsof -nP -iTCP:8765 -sTCP:LISTEN || echo "(8765 free)"'

s PROCESSES
r 'ps -eo pid,ppid,etime,command | grep -Ei "whisper|kokoro|mlx|voicemode|voice_mode" | grep -v grep || echo "(none)"'

s LAUNCHD
r 'launchctl list | grep -i voicemode || echo "(no voicemode jobs)"'
r 'ls -l ~/Library/LaunchAgents/ | grep -i voicemode || echo "(no voicemode LaunchAgents)"'
for p in whisper kokoro mlx-audio; do
  r "test -f ~/Library/LaunchAgents/com.voicemode.$p.plist && plutil -p ~/Library/LaunchAgents/com.voicemode.$p.plist || echo '(no $p plist)'"
done

s SERVICE_TREE
r 'ls -la ~/.voicemode/ 2>&1'
r 'ls -la ~/.voicemode/services/ 2>&1 || echo "(no services dir)"'
r 'find ~/.voicemode/services -maxdepth 3 -type d 2>/dev/null | head -60 || echo "(none)"'
r 'ls -la ~/.voicemode/services/whisper/models/ 2>&1 || echo "(no whisper models dir)"'
r 'test -x ~/.voicemode/services/whisper/build/bin/whisper-server && echo "whisper-server EXISTS and is executable" || echo "whisper-server MISSING or not executable"'
r 'cat ~/.voicemode/services/whisper/bin/start-whisper-server.sh 2>&1 | head -40 || echo "(no start script)"'

s CONFIG
r 'ls -la ~/.voicemode/*.env 2>&1'
r 'cat ~/.voicemode/voicemode.env 2>&1 || echo "(no global voicemode.env)"'
r 'ls -la .voicemode.env voicemode.env .voicemode/ 2>&1 || echo "(no project config here)"'

s TILDE_BUG
r 'ls -la "/Users/ibhatt/Downloads/voicemode/~" 2>&1 || echo "(no literal tilde dir in workspace)"'
r 'find /Users/ibhatt/Downloads/voicemode -maxdepth 1 -name "~*" 2>/dev/null || echo "(none at depth 1)"'
r 'ls -la ~/voicemode_debug.log 2>&1 || echo "(no home debug log)"'

s LOGS
r 'ls -la ~/.voicemode/logs/ 2>&1 || echo "(no logs dir)"'
r 'ls -la ~/.voicemode/logs/events/ 2>&1 | tail -5'
r 'ls -la ~/.voicemode/transcriptions/ 2>&1 | tail -5 || echo "(no transcriptions dir)"'
r 'ls -la ~/.voicemode/jobs/ 2>&1 | tail -5 || echo "(no jobs dir)"'

s CLI_SURFACE
r 'voicemode --help'
r 'voicemode service --help'
r 'voicemode whisper --help'
r 'voicemode kokoro --help'
r 'voicemode config --help'

s STATUS
r 'voicemode status'

print -r -- ""
print -r -- "audit written to: $OUT"
print -r -- "lines: $(wc -l <"$OUT")"
