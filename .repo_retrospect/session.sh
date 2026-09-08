#!/usr/bin/env zsh
# Shared collaborative session for VoiceMode observation work.
#
# You run:   source _inspect/session.sh
# Then:      vm <command>       # runs it, echoes it, and records it to the log
#            vmlog              # show the log
#
# Everything vm runs is appended to _inspect/observations/session-<date>.log
# so the agent can read the exact command, output, and exit code you saw.

VM_SESSION_LOG="${0:A:h}/observations/session-$(date +%Y-%m-%d).log"
mkdir -p "${VM_SESSION_LOG:h}"

vm() {
  local ts cmd rc
  ts=$(date '+%H:%M:%S')
  cmd="$*"
  {
    print -r -- ""
    print -r -- "### $ts  \$ $cmd"
  } >>"$VM_SESSION_LOG"

  print -r -- "\$ $cmd"
  eval "$cmd" 2>&1 | tee -a "$VM_SESSION_LOG"
  rc=${pipestatus[1]}

  print -r -- "### exit=$rc" >>"$VM_SESSION_LOG"
  print -r -- "[exit $rc]"
  return $rc
}

vmlog() { cat "$VM_SESSION_LOG"; }

print -r -- "shared session ready — log: $VM_SESSION_LOG"
print -r -- "use:  vm <command>    e.g.  vm voicemode --version"
