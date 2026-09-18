#!/usr/bin/env bash
# PostToolUse hook — auto-fix ruff lint on an edited Python file.
#
# Input: the tool-call JSON is provided on stdin. We read tool_input.file_path and, if it
# is a *.py file that exists, run `ruff check --fix` on it. Best-effort formatting only:
# this hook never blocks an edit (it always exits 0).
set -uo pipefail

payload="$(cat)"
file="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
' 2>/dev/null || true)"

case "$file" in
  *.py)
    if [ -f "$file" ]; then
      uv run ruff check --fix "$file" >/dev/null 2>&1 || true
    fi
    ;;
esac

exit 0
