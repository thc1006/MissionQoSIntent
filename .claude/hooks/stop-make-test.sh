#!/usr/bin/env bash
# Stop hook — block the turn from ending until `make test` is green.
#
# Input: JSON on stdin including `stop_hook_active` (true once this hook has already fired
# and forced a continuation — used to avoid an infinite stop -> retry -> stop loop).
#   green  -> exit 0 (allow stop)
#   red    -> print the failing tail to stderr + exit 2 (blocks stop; feedback goes to Claude)
#   active -> exit 0 (loop guard)
set -uo pipefail

payload="$(cat)"
active="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print(str(json.load(sys.stdin).get("stop_hook_active", False)))
except Exception:
    print("False")
' 2>/dev/null || echo False)"

if [ "$active" = "True" ]; then
  exit 0
fi

log="$(mktemp)"
if make test >"$log" 2>&1; then
  rm -f "$log"
  exit 0
fi

{
  echo "Stop blocked: 'make test' is red — fix the failing tests before ending the turn."
  echo "----- tail of 'make test' output -----"
  tail -n 25 "$log"
} >&2
rm -f "$log"
exit 2
